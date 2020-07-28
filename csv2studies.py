#!/usr/bin/env python
import csv
import json
import re

import pydicom

StudyName = "Supplement142"
Studies = {StudyName: {}}
Study = Studies[StudyName] = {"RemovePrivateTags": True, "AnonymizeTag": {}, "AnonymizeVR": {}}

with open('Supplement142.csv', encoding="utf-8-sig") as csvfile:
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in reader:
        tag = re.sub('[^0-9A-F]', '', row[0])
        keyword = pydicom.datadict.keyword_for_tag(tag)
        Study['AnonymizeTag'][keyword] = {}
        Study['AnonymizeTag'][keyword]["action"] = row[2]

print(json.dumps(Studies))
