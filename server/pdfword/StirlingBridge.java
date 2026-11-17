import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import org.apache.pdfbox.Loader;
import org.apache.pdfbox.pdmodel.PDDocument;
import stirling.software.officeconvert.OfficeConvert;

/** Local, headless adapter. Input policy and output acceptance live outside the engine. */
public final class StirlingBridge {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) throw new IllegalArgumentException("input.pdf output.docx");
        var settings = OfficeConvert.Settings.defaults().timeout(Duration.ofSeconds(120));
        try (PDDocument document = Loader.loadPDF(Path.of(args[0]).toFile());
             OutputStream output = Files.newOutputStream(Path.of(args[1]), StandardOpenOption.CREATE_NEW)) {
            if (document.isEncrypted()) throw new IllegalArgumentException("Encrypted input");
            OfficeConvert.convert(document, output, OfficeConvert.Format.DOCX, settings);
        }
    }
}
