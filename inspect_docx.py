import zipfile
from xml.etree import ElementTree as ET

path = r'C:\Users\Sanskar\OneDrive\Desktop\Internship\Trade_Stock_Project-main\Trade_Stock_Project-main\Testing_Report_Simple.docx'
with zipfile.ZipFile(path) as z:
    root = ET.fromstring(z.read('word/document.xml'))
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
paras = []
for p in root.findall('.//w:p', ns):
    text = ''.join(t.text or '' for t in p.findall('.//w:t', ns))
    if text.strip():
        paras.append(text)
for i, para in enumerate(paras, 1):
    print(f'{i}: {para}')
