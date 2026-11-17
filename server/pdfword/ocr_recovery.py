"""Lossless horizontal crop partitioning for a truncated text-block retry."""
import math


def recovery_options(options):
    if not options or 'repetition_penalty' not in options:
        return {}
    value = options['repetition_penalty']
    if type(value) not in (int, float) or not math.isfinite(value) or not 1 <= value <= 1.2:
        raise ValueError('Unsupported OCR repetition recovery')
    return {'repetition_penalty': value}


def text_bands(image):
    """Only cut wide horizontal whitespace; keep every pixel exactly once.

    Small gaps between pronunciation marks and base characters remain together.
    No thresholded image is sent to recognition and no band is discarded.
    """
    import numpy as np
    width, height = image.size
    if width < 80 or height < 64 or width * height > 16000000:
        return []
    blank = (np.asarray(image.convert('L')) < 180).sum(axis=1) <= 2
    minimum_gap = max(4, round(height * .015))
    cuts = [0]
    start = None
    for index, empty in enumerate(list(blank) + [False]):
        if empty and start is None:
            start = index
        if not empty and start is not None:
            if start > 0 and index < height and index-start >= minimum_gap:
                cuts.append((start+index)//2)
            start = None
    cuts.append(height)
    # Underlines can create a short isolated band between two whitespace
    # gaps. Keep that ink with the preceding line instead of rejecting the
    # entire partition (or recognizing the underline as separate text).
    index = 1
    while index < len(cuts)-1:
        if cuts[index+1]-cuts[index] < 24:
            cuts.pop(index)
        else:
            index += 1
    if not 3 <= len(cuts) <= 13 or any(b-a < 16 for a,b in zip(cuts,cuts[1:])):
        return []
    return [image.crop((0,a,width,b)) for a,b in zip(cuts,cuts[1:])]


def recognize_block(infer, image, prompt, cap, options=None):
    options = recovery_options(options)
    bands = text_bands(image) if prompt == 'Recognize the content of the image.' else []
    if bands and options.get('repetition_penalty', 1) > 1:
        outputs = [infer(band, prompt, min(cap, 2048), options) for band in bands]
        return '\n'.join(text for text, _ in outputs), any(hit for _, hit in outputs)
    return infer(image, prompt, min(cap, 2048) if bands else cap, options)


class RepetitionStop:
    """Request a bounded retry for a sustained generated-text cycle.

    This is never successful completion. The caller must mark this attempt
    truncated and still require a complete retry or reject the page. Normal
    EOS keeps its original behavior; numeric/punctuation runs are not cycles.
    """
    def __init__(self, eos, decode):
        from collections import deque
        self.eos = eos
        self.decode = decode
        self.tokens = deque(maxlen=256)
        self.repeated = False
        self.count = 0

    def __call__(self, token):
        if self.eos(token):
            return True
        self.tokens.append(token)
        self.count += 1
        if self.count < 128 or self.count % 16:
            return False
        values = tuple(self.tokens)
        for period in range(1, 17):
            repetitions = max(8, math.ceil(128 / period))
            length = period * repetitions
            if length > len(values):
                continue
            pattern = values[-period:]
            if (values[-length:] == pattern * repetitions
                    and any(c.isalpha() for c in self.decode(list(pattern)))):
                self.repeated = True
                return True
        return False


def bounded_generate(generate, model, processor, text, image, cap, options=None,
                     guard_repetition=False):
    """Preserve the tokenizer's EOS state across both successful and failed calls."""
    generation_options = recovery_options(options)
    guard = None
    if guard_repetition:
        tokenizer = processor.tokenizer if hasattr(processor, 'tokenizer') else processor
        original_stop = tokenizer.stopping_criteria
        original_stop.reset(model.config.eos_token_id)
        guard = RepetitionStop(original_stop, tokenizer.decode)
        generation_options['stopping_criteria'] = guard
    try:
        out = generate(model, processor, text, image=[image], max_tokens=cap,
                       temperature=0, **generation_options)
    finally:
        if guard is not None:
            tokenizer.stopping_criteria = original_stop
    return out, out.generation_tokens >= cap or (guard is not None and guard.repeated)
