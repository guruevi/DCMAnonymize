
This script anonymizes medical DICOM images in a directory (incoming) and copies the
anonymized version into (outgoing) for research studies.

The script can receive DICOMs from many modalities. Each modality may have its own
intricacies on how it identifies a DICOM as part of a particular research study.

Make sure to change RANDOM_UUID and other salts in the studies.json
If you don't and publish data or disclose the values contained in the scripts after
making public the anonymized data, you will have a potential breach of confidentiality.

stations.json: <-- This files contains StationName definitions
<pre>
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
</pre>

studies.json: <-- This file contains the Studies definition

PLEASE NOTE: This file may contain information that allows you to re-identify a particular series or study
             For HIPAA compliance you may have to blind the contents of these values to the researcher
             Make sure to modify any salts and do not upload this file to a public place for the same reasons.
             If this file becomes compromised after publishing data, you may have to disclose a breach
<pre>{
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
}</pre>
