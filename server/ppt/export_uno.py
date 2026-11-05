"""Runs inside the disposable offline core container; no host Office integration."""
import json
import subprocess
import sys
import time
import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.document.MacroExecMode import NEVER_EXECUTE
from com.sun.star.document.UpdateDocMode import NO_UPDATE


def prop(name, value):
    result = PropertyValue()
    result.Name, result.Value = name, value
    return result


def export(source, destination):
    process = subprocess.Popen([
        'soffice', '-env:UserInstallation=file:///tmp/ppt-profile', '--headless',
        '--norestore', '--nodefault', '--nofirststartwizard',
        '--accept=pipe,name=pptconvert;urp;StarOffice.ComponentContext',
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    document = None
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
        context = None
        for _ in range(100):
            try:
                context = resolver.resolve('uno:pipe,name=pptconvert;urp;StarOffice.ComponentContext')
                break
            except Exception:
                time.sleep(.1)
        if context is None:
            raise RuntimeError('Office startup failed')
        desktop = context.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', context)
        document = desktop.loadComponentFromURL(uno.systemPathToFileUrl(source), '_blank', 0, (
            prop('Hidden', True), prop('ReadOnly', True), prop('MacroExecutionMode', NEVER_EXECUTE),
            prop('UpdateDocMode', NO_UPDATE),
        ))
        if document is None or not document.supportsService('com.sun.star.presentation.PresentationDocument'):
            raise RuntimeError('Not a presentation')
        pages = document.getDrawPages()
        visible = sum(bool(pages.getByIndex(i).Visible) for i in range(pages.Count))
        if not 1 <= visible <= 200:
            raise RuntimeError('Invalid visible slide count')
        settings = (
            prop('ExportHiddenSlides', False), prop('ExportNotes', False),
            prop('ExportNotesPages', False), prop('ExportOnlyNotesPages', False),
            prop('ExportNotesInMargin', False), prop('IsAddStream', False),
            prop('UseTransitionEffects', False), prop('ExportFormFields', False),
            prop('ReduceImageResolution', False), prop('SelectPdfVersion', 0),
        )
        document.storeToURL(uno.systemPathToFileUrl(destination), (
            prop('FilterName', 'impress_pdf_Export'), prop('Overwrite', True),
            prop('FilterData', uno.Any('[]com.sun.star.beans.PropertyValue', settings)),
        ))
        print(json.dumps({'visible': visible}))
    finally:
        if document is not None:
            document.close(True)
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == '__main__':
    export(sys.argv[1], sys.argv[2])
