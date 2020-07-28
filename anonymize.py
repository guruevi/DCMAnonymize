"""
Anonymize DICOM directory

author : Evi Vanoost <vanooste@rcbi.rochester.edu>
license : MIT

This script anonymizes medical DICOM images in a directory (incoming) and copies the
anonymized version into (outgoing) for research studies.

The script can receive DICOMs from many modalities. Each modality may have its own
intricacies on how it identifies a DICOM as part of a particular research study.

Make sure to change RANDOM_UUID and other salts in the studies.json
If you don't and publish data or disclose the values contained in the scripts after
making public the anonymized data, you will have a potential breach of confidentiality.

stations.json: <-- This files contains StationName definitions
{
 "default": { <-- Station Name (default is the one it picks if none are defined)
    "TagForStudy": "ProtocolName", <-- Which DICOM tag identifies the research study
    "Split": null <-- Whether the DICOM tag contains a compounded name
  }
 "MRC12345": {
    "TagForStudy": "StudyDescription", <-- Our Siemens uses StudyDescription
    "Split": "^", <-- And then the name of the study is compounded as such: STUDYNAME^PROTOCOL
    "SplitIndex": 0 <-- So if you split, which part is the study name (starting at 0)
  }
}

studies.json: <-- This file contains the Studies definition
PLEASE NOTE: This file may contain information that allows you to re-identify a particular series or study
             For HIPAA compliance you may have to blind the contents of these values to the researcher
             Make sure to modify any salts and do not upload this file to a public place for the same reasons.
             If this file becomes compromised after publishing data, you may have to disclose a breach
{
  "Supplement142": { <-- Name of the Study (eg. ProtocolName), defaults to Supplement142
     "RemovePrivateTags": true, <-- Whether to remove "Private" (non-default) DICOM tags
     "AnonymizeTag": { <-- This contains all the tags that need to be anonymized
                            Tag Definitions has priority over VR definitions,
                            so you can set the default action on eg. PN VR but modify behavior
                            for one or more tag
        "AccessionNumber": { <-- DICOM tag
            "action": "clear" <-- Which action to take on the tag
                    Valid actions:
                        delete -> Delete the Tag
                        clear -> Clear/Empty the Tag (set to None)
                        hash -> Hash the value, optionally specify salt to salt with a specific string
                            otherwise global variable RANDOM_UUID will be used
                         { "action": "hash", "salt": "astring" }
                        keep -> Keep the Tag as-is
                        value -> Set the Tag to a specific value, pass value or None will be used
                            { "action": "value", "value": "string" }
                        offset -> Offset the tag with a value (not built yet)
                        regen -> Regenerate the UID using generate_uid() -
                                 ALL matching UID in the DICOM file and directory being processed will
                                 convert to the same regenerated UID (to keep sequences sane)
                                 Unless you implement some storage on the ORIGINAL_UID variable,
                                 the UID will be different every time you run the script
                                 This may be necessary if you trigger for every series instead of every study.
                                 You can make the regeneration deterministic by specifying entropy_src
                                 (eg. a relevant tag with original private data)
                                 https://pydicom.github.io/pydicom/dev/reference/generated/pydicom.uid.generate_uid.html

        },
        ...
     },
     "AnonymizeVR": { <-- Any VR you want to wholly anonymize within the script. Any VR works.
                            for the UI VR you should probably specify 'regen'
        "PN": {
          "action": "hash"
        }
     }
}


"""
import datetime
import hashlib
import json
import os

import pydicom
from pydicom.data import get_testdata_files
from pydicom.errors import InvalidDicomError
from pydicom.uid import generate_uid

# Getting the current work directory (cwd)
indir = "./incoming/"
outdir = "./outgoing/"
filenames = []
# r=root, d=directories, f = files
for r, d, f in os.walk(indir):
    for file in f:
        filenames.append(os.path.join(r, file))

if not filenames:
    exit()

with open('studies.json') as json_file:
    studies = json.load(json_file)

with open('stations.json') as json_file:
    stations = json.load(json_file)

# You should change this seed for your environment
RANDOM_UUID = "be76acfcfdb04e64ba7525dbf745fe5f"
# If you want UUID's to be consistently translated, you may want to implement a lookup table
ORIGINAL_UUID = {}


def hashtext(text, salt):
    return hashlib.sha256(salt.encode() + text.encode()).hexdigest()


def regenuid(element):
    ORIGINAL_UUID[element] = ORIGINAL_UUID.get(element, generate_uid())
    return ORIGINAL_UUID[element]


for filename in filenames:
    # Make sure we have a valid DICOM
    try:
        dataset = pydicom.filereader.dcmread(filename)
    except InvalidDicomError:
        print("Error: " + filename +
              " is missing DICOM File Meta Information header or the 'DICM' prefix is missing from the header.")
        continue

    # Find Station Name, each Station has different methods of encoding Study Names
    try:
        StationName = dataset.data_element('StationName').value
        StationInfo = stations.get(StationName, stations.get("default"))
    except KeyError:
        print("Error: " + filename + " is missing StationName")
        continue

    # Find Study Name, each Study may have separate de-identification methods
    try:
        StudyName = dataset.data_element(StationInfo['TagForStudy']).value
        if StationInfo['Split']:
            x = StudyName.split(StationInfo['Split'])
            StudyName = x[StationInfo.get('SplitIndex', 0)]
        StudyInfo = studies.get(StudyName, studies.get("Supplement142"))
    except KeyError:
        print("Error: " + filename + " is missing " + StationInfo['TagForStudy'])
        continue

    print("Processing: " + filename)
    print("Study: " + StudyName)

    if StudyInfo['RemovePrivateTags']:
        print("Removing Private Tags")
        dataset.remove_private_tags()

    TagDefs = StudyInfo['AnonymizeTag']
    VRDefs = StudyInfo['AnonymizeVR']
    for de in dataset.iterall():
        tag = pydicom.datadict.get_entry(de.tag)[4]
        if tag in TagDefs or de.VR in VRDefs:
            if tag in TagDefs:
                action = TagDefs[tag].get('action', 'delete')
            else:
                action = VRDefs[de.VR].get('action', 'delete')

            print("   " + tag + " -> " + action)
            if action == "delete":
                try:
                    delattr(dataset, tag)
                except AttributeError:
                    print("Parent Deleted: " + tag)
            elif action == "clear":
                de.value = None
            elif action == "hash":
                salt = TagDefs[tag].get('salt', RANDOM_UUID)
                de.value = hashtext(dataset.data_element(tag).value, salt)
            elif action == "value":
                de.value = TagDefs[tag].get('value', None)
            elif action == "offset":
                print("Offsetting a " + de.VR + " Type Not Implemented")
            elif action == "regen":
                de.value = regenuid(de.value)
            elif action == "keep":
                pass
            else:
                print("Tag Action Not Implemented")

    for de in dataset.iterall():
        print(de)

    # This is a prerequisite
    dataset.file_meta.MediaStorageSOPInstanceUID = regenuid(dataset.file_meta.MediaStorageSOPInstanceUID)

    i = 0
    while os.path.exists(os.path.join(outdir, "ANON%05d.DCM" % i)):
        i += 1
    dataset.save_as(os.path.join(outdir, "ANON%05d.DCM" % i))
    os.remove(filename)
