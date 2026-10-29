"""A native model fault must not share the navigation process."""
from pathlib import Path
import xml.etree.ElementTree as E
r=Path(__file__).resolve().parents[1]
a='{http://schemas.android.com/apk/res/android}'
root=E.parse(r/'app/src/main/AndroidManifest.xml').getroot()
s=[e for e in root.iter('service') if e.get(a+'name')=='.vision.CpLaneNativeService']
assert len(s)==1 and s[0].get(a+'process')==':cp_lane' and s[0].get(a+'exported')=='false'
print('CP lane runtime isolated from navigation')
