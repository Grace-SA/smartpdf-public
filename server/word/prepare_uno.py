"""Inside the disposable converter only. Local UNO pipe; no TCP listener."""
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid
import os
import signal
import zipfile
import posixpath
from xml.dom import minidom

def omit_comments(source, output):
    """Remove annotation parts/markers from a copy before Office imports it."""
    word = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    relationships = 'http://schemas.openxmlformats.org/package/2006/relationships'
    kinds = {'comments', 'commentsExtended', 'commentsExtensible', 'commentsIds', 'person', 'people'}
    removed = set()
    with zipfile.ZipFile(source) as package:
        entries = package.infolist()
        for entry in entries:
            if not entry.filename.endswith('.rels'): continue
            doc = minidom.parseString(package.read(entry))
            owner = posixpath.dirname(posixpath.dirname(entry.filename))
            for relation in doc.getElementsByTagName('*'):
                if relation.namespaceURI == relationships and relation.localName == 'Relationship' and relation.getAttribute('Type').rsplit('/',1)[-1] in kinds:
                    target = relation.getAttribute('Target')
                    removed.add(posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(owner,target)))
            doc.unlink()
        removed.update(posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels') for name in list(removed))
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as result:
            for entry in entries:
                if entry.filename in removed: continue
                data = package.read(entry)
                if entry.filename.endswith(('.xml','.rels')):
                    doc = minidom.parseString(data)
                    for node in list(doc.getElementsByTagName('*')):
                        remove = (node.namespaceURI == word and node.localName in {'comment','commentRangeStart','commentRangeEnd','commentReference'})
                        if node.namespaceURI == relationships and node.localName == 'Relationship' and node.getAttribute('Type').rsplit('/',1)[-1] in kinds: remove = True
                        if entry.filename == '[Content_Types].xml' and node.getAttribute('PartName').lstrip('/') in removed: remove = True
                        if remove and node.parentNode: node.parentNode.removeChild(node)
                    data = doc.toxml(encoding='utf-8');doc.unlink()
                result.writestr(entry.filename,data)

def prepare(source, output, options):
    import uno
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output: raise RuntimeError('Original documents must not be overwritten')
    if options.get('omitComments'):
        omit_comments(source,output)
        if not options.get('_hasRevisions'): return
        intermediate = output.with_name('annotations-removed.docx')
        output.replace(intermediate)
        source = intermediate
    pipe = 'smartpdf_' + uuid.uuid4().hex
    process = subprocess.Popen(['soffice', '-env:UserInstallation=file:///tmp/' + pipe,
        '--headless', '--norestore', '--nodefault', '--nofirststartwizard',
        '--accept=pipe,name=' + pipe + ';urp;StarOffice.ServiceManager'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    doc = None
    desktop = None
    def prop(name, value):
        item = uno.createUnoStruct('com.sun.star.beans.PropertyValue')
        item.Name, item.Value = name, value
        return item
    try:
        local = uno.getComponentContext()
        resolver = local.ServiceManager.createInstanceWithContext('com.sun.star.bridge.UnoUrlResolver', local)
        for _ in range(120):
            try:
                context = resolver.resolve('uno:pipe,name=' + pipe + ';urp;StarOffice.ComponentContext')
                break
            except Exception:
                if process.poll() is not None: raise RuntimeError('Office preparation unavailable') from None
                time.sleep(.25)
        else: raise RuntimeError('Office preparation unavailable')
        desktop = context.ServiceManager.createInstanceWithContext('com.sun.star.frame.Desktop', context)
        doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(str(source)), '_blank', 0,
            (prop('Hidden', True), prop('ReadOnly', False),
             prop('MacroExecutionMode', uno.getConstantByName('com.sun.star.document.MacroExecMode.NEVER_EXECUTE')),
             prop('UpdateDocMode', uno.getConstantByName('com.sun.star.document.UpdateDocMode.NO_UPDATE'))))
        if doc is None: raise RuntimeError('Document could not be loaded')
        view = options.get('revisionView', 'unchanged')
        if options.get('_hasRevisions') and not doc.getRedlines().getCount() and view == 'original':
            raise RuntimeError('Original revision state could not be represented')
        if view in {'final', 'original'}:
            dispatch = context.ServiceManager.createInstanceWithContext('com.sun.star.frame.DispatchHelper', context)
            dispatch.executeDispatch(doc.getCurrentController().getFrame(),
                '.uno:AcceptAllTrackedChanges' if view == 'final' else '.uno:RejectAllTrackedChanges', '', 0, ())
        if doc.getRedlines().getCount(): raise RuntimeError('Unresolved document revisions')
        def annotations():
            iterator = doc.getTextFields().createEnumeration()
            values = []
            while iterator.hasMoreElements():
                field = iterator.nextElement()
                if field.supportsService('com.sun.star.text.TextField.Annotation'): values.append(field)
            return values
        if options.get('omitComments'):
            for annotation in annotations(): annotation.dispose()
        if annotations(): raise RuntimeError('Unresolved document comments')
        doc.storeAsURL(uno.systemPathToFileUrl(str(output)),
            (prop('FilterName', 'Office Open XML Text'), prop('Overwrite', True)))
    finally:
        if doc is not None:
            try: doc.close(True)
            except Exception: pass
        if desktop is not None:
            try: desktop.terminate()
            except Exception: pass
        try: os.killpg(process.pid,signal.SIGTERM)
        except ProcessLookupError: pass
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=5)

if __name__ == '__main__':
    try:
        prepare(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
    except Exception:
        # Never expose author names, paths, fields, annotation text or stacks.
        print(json.dumps({'error': 'The selected document view could not be prepared.'}))
        sys.exit(2)
