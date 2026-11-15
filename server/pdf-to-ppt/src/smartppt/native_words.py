"""Retry native layout at word granularity with complete text and glyph gates."""
from contextlib import closing
from copy import deepcopy
from collections import Counter
import ctypes
from pathlib import Path
import shutil
import tempfile
import pypdfium2 as pdfium
from pptx import Presentation
from .config import ConversionError
from .layout import extract_native
from .quality import normalized
from .regional import draw_objects,calibrate_runs,rendered_word_regions
from .render_gate import render_presentations,metric,accept_candidate
from .selected_render import render_selected,location,page_metric


def refine_sparse_shapes(slide,targets,observed):
    """Retry at most three residual words, without changing any text.

    Font hinting and character-spacing quantization can leave a small residual
    after the first optical fit. Every failed word must have a bounded fit;
    otherwise leave the whole page's candidate unchanged.
    """
    from pptx.shapes.autoshape import Shape
    from .ocr_fit import fit_shape
    failed=[t for t in targets if t['shape'] not in observed or
            max(abs(a-b) for a,b in zip(t['bbox'],observed[t['shape']]))>2]
    if not failed or len(failed)>3:return 0
    pending=[]
    for target in failed:
        if target['shape'] not in observed:return 0
        shape=slide.shapes[target['shape']]
        if not shape.has_text_frame:return 0
        candidate=Shape(deepcopy(shape._element),slide.shapes)
        if not fit_shape(candidate,target['bbox'],observed[target['shape']]):return 0
        pending.append((shape,candidate))
    for shape,candidate in pending:shape._element.getparent().replace(shape._element,candidate._element)
    return len(pending)


def refine_sparse_words(path,prs,pages,candidates,rendered,folder,settings):
    from .table_layout import word_targets
    from .ocr_fit import observed_boxes
    outputs={number:rendered for number in candidates};evidence={}
    for iteration in range(2):
        probe=Presentation(path);changed={}
        for number,(parts,_) in candidates.items():
            targets=word_targets(probe,pages[number],parts);output,index=location(outputs[number],number)
            with pdfium.PdfDocument(output) as doc,closing(doc[index]) as page:
                observed=observed_boxes(page,probe.slides[number-1],targets)
            count=refine_sparse_shapes(probe.slides[number-1],targets,observed)
            if count:changed[number]=count
        if not changed:break
        candidate=folder/f'word-residual-{iteration}.pptx';probe.save(candidate)
        try:measured=render_selected([candidate],folder,settings,tuple(sorted(changed)))[0]
        except ConversionError:break
        prs,path=probe,candidate
        for number,count in changed.items():
            outputs[number]=measured
            record=evidence.setdefault(number,{'passes':0,'word_adjustments':0})
            record['passes']+=1;record['word_adjustments']+=count
    return prs,path,outputs,evidence


def join_word_fragments(runs):
    """Keep a literal word/number together across adjacent PDF text objects.

    A textbox boundary becomes a newline in exported text. Never insert that
    boundary inside a source number such as 2012 or 21.2. Literal whitespace,
    style changes, rotated text and line changes remain boundaries.
    """
    result=[]
    for run in runs:
        item=dict(run,object_ids=[run['object_id']]);previous=result[-1] if result else None
        if previous:
            a,b=previous['box'],run['box'];size=run['size']
            compatible=(previous['end_index']==run['index'] and
                        not previous['text'][-1].isspace() and not run['text'][0].isspace() and
                        not previous.get('rotation') and not run.get('rotation') and
                        abs(previous['size']-size)<.01 and
                        all(previous[k]==run[k] for k in ('font','source_font','source_base_font','bold','italic','color')) and
                        previous['baseline'] is not None and run['baseline'] is not None and
                        abs(previous['baseline']-run['baseline'])<=size*.08 and
                        -.1*size<=b[0]-a[2]<=size*.8)
            if compatible:
                previous['text']+=run['text'];previous['end_index']=run['end_index']
                previous['object_ids'].append(run['object_id'])
                previous['box']=[min(a[0],b[0]),min(a[1],b[1]),max(a[2],b[2]),max(a[3],b[3])]
                continue
        result.append(item)
    return result


def repair_native_words(source,target,report,settings,trim_spacing=False):
    eligible=[p for p in report['pages'] if p['route'] in ('native-coordinate','stirling-table','stirling-retained','stirling-retained-visual','source-image-fallback','native-regions') and p.get('text_granularity')!='word']
    if trim_spacing:eligible=[p for p in eligible if p.get('word_layout_attempt',{}).get('accepted') is False]
    if not eligible:return report
    with tempfile.TemporaryDirectory(prefix='smartppt-word-layout-',dir=Path(source).parent) as tmp,pdfium.PdfDocument(source) as doc:
        folder=Path(tmp);prs=Presentation(target);pages={};candidates={}
        def render(files):
            selection=tuple(sorted(candidates))
            if len(selection)<len(doc):return render_selected(files,folder,settings,selection)
            return render_presentations(files,folder,settings)
        try:
            for item in eligible:
                number=item['page'];page=pages[number]=doc[number-1]
                runs,objects,warnings=extract_native(page,split_words=True,allow_quarter_turns=True)
                if not runs or len(runs)>3000:continue
                with closing(page.get_textpage()) as tp:reference=tp.get_text_range()
                # Never improve apparent coverage by dropping hidden, clipped,
                # unresolved or rotated source characters from the denominator.
                if normalized(''.join(r['text'] for r in runs))!=normalized(reference):continue
                runs=join_word_fragments(runs)
                lookup={ctypes.cast(obj.raw,ctypes.c_void_p).value:obj for obj in objects}
                parts=[([lookup[p] for p in dict.fromkeys(r['object_ids'])],[r]) for r in runs]
                candidates[number]=(parts,warnings)
                draw_objects(prs,prs.slides[number-1],page,parts)
            if not candidates:return report
            before=folder/'before.pptx';candidate=folder/'candidate.pptx'
            shutil.copyfile(target,before);prs.save(candidate)
            baseline_pdf,rendered=render([before,candidate])
            fallback=Presentation(target)
            # Keep already-correct paragraphs and semantic tables. Word boxes
            # are a repair for misplaced text, not a blanket conversion policy.
            for number,(parts,_) in list(candidates.items()):
                geometry=rendered_word_regions(prs,number,pages[number],parts,baseline_pdf)
                baseline_path,baseline_index=location(baseline_pdf,number)
                with pdfium.PdfDocument(baseline_path) as base,closing(base[baseline_index]) as page,closing(page.get_textpage()) as tp:
                    reference=''.join(r['text'] for _,runs in parts for r in runs)
                    complete=Counter(normalized(tp.get_text_range()))==Counter(normalized(reference))
                if complete and all(boxes is not None for boxes in geometry):
                    del candidates[number]
                    slide=prs.slides[number-1]
                    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                    for shape in fallback.slides[number-1].shapes:
                        slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
            if not candidates:return report
            for number,(parts,_) in candidates.items():
                calibrate_runs(prs,number,pages[number],parts,rendered,trim_spacing=trim_spacing)
                draw_objects(prs,prs.slides[number-1],pages[number],parts)
            calibrated=folder/'calibrated.pptx';prs.save(calibrated)
            rendered=render([calibrated])[0]
            prs,calibrated,word_renders,residuals=refine_sparse_words(calibrated,prs,pages,candidates,rendered,folder,settings)
            # A valid word layout can supply surrounding text without forcing
            # an existing table to lose its cells. Measure that hybrid separately.
            table_parts={number:parts for number,(parts,_) in candidates.items()
                         if any(s.has_table for s in fallback.slides[number-1].shapes)
                         and all(rendered_word_regions(prs,number,pages[number],parts,word_renders[number]))
                         and accept_candidate(page_metric(source,baseline_pdf,number),page_metric(source,word_renders[number],number))}
            from .table_layout import try_restore_tables
            tables,table_prs=try_restore_tables(calibrated,fallback,source,pages,table_parts,baseline_pdf,settings,folder) if table_parts else ({},None)
            accepted=0
            for item in eligible:
                number=item['page']
                if number not in candidates:continue
                parts,warnings=candidates[number]
                geometry=rendered_word_regions(prs,number,pages[number],parts,word_renders[number])
                old,new=page_metric(source,baseline_pdf,number),page_metric(source,word_renders[number],number)
                passed=all(boxes is not None for boxes in geometry) and accept_candidate(old,new)
                evidence={'spacing_retry':trim_spacing,'accepted':passed,'words':len(parts),'position_passed':sum(b is not None for b in geometry),'position_tolerance_points':2,'baseline':old,'candidate':new}
                if number in residuals:evidence['residual_calibration']=residuals[number]
                if not passed:
                    slide=prs.slides[number-1]
                    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                    for shape in fallback.slides[number-1].shapes:
                        slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                    item['word_layout_attempt']=evidence
                    continue
                previous=deepcopy(item);runs=[r for _,rs in parts for r in rs];accepted+=1
                item.clear();item.update(page=number,route='native-coordinate',text_granularity='word',editable_runs=len(runs),
                    source_text_characters=sum(len(r['text']) for r in runs),word_layout_attempt=evidence,prior_attempt=previous,
                    font_substitutions=sorted({r['source_font']+' → '+r['font'] for r in runs if r['substituted']}),
                    warnings=warnings,graphics='raster; not editable')
                if number in tables:
                    slide=prs.slides[number-1]
                    for shape in list(slide.shapes):shape._element.getparent().remove(shape._element)
                    for shape in table_prs.slides[number-1].shapes:
                        slide.shapes._spTree.insert_element_before(deepcopy(shape._element),'p:extLst')
                    item.update(route='stirling-table',text_granularity='cell',table_layout=tables[number],
                                graphics='original graphics; semantics not verified')
                    item['warnings'].append('table_layout_requires_review')
                elif any(s.has_table for s in fallback.slides[number-1].shapes):
                    item['warnings'].append('table_rebuilt_as_positioned_text')
            if accepted:
                final=folder/'verified.pptx';prs.save(final);final.replace(target)
        finally:
            for page in pages.values():page.close()
    return report


def try_native_words(source,target,report,settings):
    # The retry is optional. Until it completes, the caller's verified package
    # is untouched; a renderer failure must not destroy that existing result.
    pending=deepcopy(report)
    try:repair_native_words(source,target,pending,settings)
    except ConversionError as error:
        report['word_layout_error']=error.code
        return report
    report.clear();report.update(pending)
    refined=deepcopy(report)
    try:repair_native_words(source,target,refined,settings,trim_spacing=True)
    except ConversionError as error:
        report['word_spacing_retry_error']=error.code
        return report
    report.clear();report.update(refined)
    return report
