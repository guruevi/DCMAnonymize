# Deterministic DICOM Anonymizer 

## (anonymize.py)

This script anonymizes medical DICOM images in a directory (provided by the first argument) and copies the
anonymized version into an outgoing folder for research studies. It then uses DCMTK's dcmsend command to send to a DICOM
receiver.

The script can process DICOMs from many modalities. Each modality may have its own intricacies on how it identifies a 
DICOM as part of a particular research study.

Make sure to change RANDOM_UUID, random.txt and other salts and seeds in the studies.json. If you don't and publish data
or disclose the values contained in the scripts after making public the anonymized data, you will have a potential 
breach of confidentiality.
 
### random.txt
A random string to override the RANDOM_UUID hardcoded in the script.
 
### stations.json
This files contains StationName definitions.
<pre>
{
 "default": { <-- Station Name (default is the one it picks if none are defined)
    "TagForStudy": "ProtocolName", <-- Which DICOM tag identifies a research study
    "Split": null <-- If the DICOM tag contains a compounded name, tell it where to split() the string
  }
 "MRC12345": { <-- This is the StationName that may send data identified in the StationName header
    "TagForStudy": "StudyDescription", <-- This Station uses StudyDescription
    "Split": "^", <-- And then the name of the study is compounded as such: STUDYNAME^PROTOCOL
    "SplitIndex": 0 <-- So if you split, which index value contains the study name (starting at 0)
  }
}
</pre>

### studies.json:
This file contains the Studies definition

####PLEASE NOTE:
All random values are deterministic based on the random seeds and fixed salts you specify in the configuration file. 
This makes the script able to regenerate the same values on every run, so longitudinal studies and inter-frame DICOM 
files can be identified and analyzed. People with access to original data as well as the anonymized may be able to 
re-identify and calculate offsets for an entire study.

Based on your locale, attempts at re-identification may be illegal (EU) or a violation of ethics and policy (HIPAA, 
GDPR)

This file may contain information that allows you to re-identify a particular series or study. For HIPAA compliance you 
may have to blind the contents of these values to the researcher. Make sure to modify any salts and do not upload this 
file to a public place for the same reasons.

**If this file becomes compromised after publishing data, you may have to disclose a breach**
            
It may thus be necessary to still run another cycle of anonymization that clears values before publishing raw data if 
you do not operate with a fully blinded study methodology.

The default index is Supplement142 which is *based* on DICOM Supplement 142: Clinical Trial De-identification Profiles 
(ftp://medical.nema.org/medical/dicom/final/sup142_ft.pdf)

<pre>{
  "Supplement142": { <-- Name of the Study (eg. ProtocolName, see stations.json), defaults to Supplement142 otherwise
     "RemovePrivateTags": true, <-- Whether to remove "Private" (non-default) DICOM tags
     "SavePrivateTags": [], <-- A list of private tags you want to keep for eg. data analysis. 
                                May be necessary to extract DTI and this may differ from scanner to scanner.
     "RandomSeed": 'a random string', <-- A random seed/salt to be used by this study, you can set one here, or uniquely 
                                          for each DICOM tag. If you set neither, the default at the top of the script
                                          will be used, which will be the same for all studies and tags that do not have
                                          a salt or seed.
     "AnonymizeTag": { <-- This contains all the tags that need to be anonymized
                           Tag Definitions have priority over VR definitions, so you can set the default action on eg. 
                           PN VR but override VR behavior for one or more tag
        "AccessionNumber": { <-- actual DICOM tag
            "action": "clear" <-- Which action to take on the tag
        },
        ...
     },
     "AnonymizeVR": { <-- Any VR you want to wholly anonymize within the script. Any VR works. For the UI VR you should 
                          probably specify 'regen'
        "PN": {
          "action": "hash",
          "salt": "arandomstring"
        }
     }
}</pre>

### Valid actions:
#### delete
Delete the tag completely, this is the default action if the tag is defined but no action is specified
#### clear
Clear/Empty the tag. The tag will still exist but will have no value.
#### hash
Hash the value (SHA256), optionally specify salt to salt with a specific string otherwise RandomSeed in the studies.json 
or the global variable RANDOM_UUID will be used (in order of preference).
<pre>{ "action": "hash", "salt": "arandomstring" }</pre>
#### keep
Keep the Tag as-is. This is the default action if the tag is not defined at all but could be used to override a VR 
action for a specific tag
#### value
Set the Tag to a specific value, pass value to specify what string it should be. If you set no value, this will have the
 same behavior as *clear*
<pre>{ "action": "value", "value": "string" }</pre>
If you set the value to *DTnow*, *DAnow* or *TMnow*, it will generate a DateTime, Date or Time string based on when the 
script started running (the entire directory will have the same time)
If the DICOM file does not have the tag already, it will be added.
#### offset
Offset the tag with a deterministic random value or a fixed offset.

Only works on DT, DA and TM VR's right now 
(TODO: Digit VR's - http://dicom.nema.org/dicom/2013/output/chtml/part05/sect_6.2.html)
                                 
**Fixed:** you should pass a number (in seconds, positive or negative) to offset the date or time
<pre>{ "action": "offset", "value": -86400 }</pre>
**Random:** you should pass a seed, the offset will be randomized (-50 and +50 years, in 1 second increments), 
deterministic based on the seed provided
{ "action": "offset", "seed": "string" }

#### regen
Regenerate the tag with a random (deterministic through seed) value.
<pre>{ "action": "offset", "seed": "string" }</pre>
**UI**: a new UID will be generated: 
https://pydicom.github.io/pydicom/dev/reference/generated/pydicom.uid.generate_uid.html

**DT, DA or TM**: A random time will be generated based on when the script started running. Intra-series dates will 
remain deterministic. If your timebase should be fixed (for inter-series and inter-study comparisons) use offset 
instead, optionally with a seed value

**TODO: Other VR's**

## studies.json generator (csv2tudies.py)
You can pass an Excel sheet to the researcher with DICOM tags (see Supplement142.csv for example) and have them 
(or your IRB) decide the action on each of the tags. Clean the data and feed it through this script and it will generate 
a JSON structure you can add to studies.json.

TODO: Generate random seed values during creation and allow for offset values to be passed from the CSV file
