#!/usr/bin/env python2
'''
Run this script to get ScanImage metadata from RAW acquisition files (.tif) from SI.
Requires ScanImageTiffReader (download: http://scanimage.vidriotechnologies.com/display/SIH/ScanImage+Home)
Assumes Linux, unless otherwise specified (see: options.path_to_si_reader)

Run python get_scanimage_data.py -h for all input options.
'''

import os
import sys
import optparse
import json
import re
import scipy.io
import numpy as np
from stat import S_IREAD, S_IRGRP, S_IROTH
from os.path import expanduser
home = expanduser("~")

def atoi(text):
    return int(text) if text.isdigit() else text

def natural_keys(text):
    return [ atoi(c) for c in re.split('(\d+)', text) ]


def main(options):
 
    parser = optparse.OptionParser()

    # PATH opts:
    parser.add_option('-P', '--sipath', action='store', dest='path_to_si_reader', default='~/Downloads/ScanImageTiffReader-1.1-Linux/share/python', help='path to dir containing ScanImageTiffReader.py')

    parser.add_option('-S', '--source', action='store', dest='source', default='/nas/volume1/2photon/data', help='source dir (root project dir containing all expts) [default: /nas/volume1/2photon/data]')
    #parser.add_option('-E', '--experiment', action='store', dest='experiment', default='', help='experiment type (parent of session dir)')
    parser.add_option('-i', '--animalid', action='store', dest='animalid', default='', help='Animal ID')

 
    parser.add_option('-s', '--session', action='store', dest='session', default='', help='session dir (format: YYYMMDD_ANIMALID')
    parser.add_option('-A', '--acq', action='store', dest='acquisition', default='FOV1', help="acquisition folder (ex: 'FOV1_zoom3x') [default: FOV1]")
    #parser.add_option('-f', '--functional', action='store', dest='functional_dir', default='functional', help="folder containing functional TIFFs. [default: 'functional']")
    parser.add_option('-r', '--run', action='store', dest='run', default='', help="name of run dir containing tiffs to be processed (ex: gratings_phasemod_run1)")

    parser.add_option('--rerun', action='store_false', dest='new_acquisition', default=True, help="set if re-running to get metadata for previously-processed acquisition")


    (options, args) = parser.parse_args(options) 

    new_acquisition = options.new_acquisition
    if new_acquisition is False:
        print "This is a RE-RUN."

    path_to_si_reader = options.path_to_si_reader

    source = options.source
    animalid = options.animalid
    #experiment = options.experiment
    session = options.session
    acquisition = options.acquisition
    run = options.run
    #functional_dir = options.functional_dir

    # -------------------------------------------------------------
    # Set basename for files created containing meta/reference info:
    # -------------------------------------------------------------
    raw_simeta_basename = 'SI_%s' % run #functional_dir
    reference_info_basename = 'reference_%s' % run #functional_dir
    # -------------------------------------------------------------
    # -------------------------------------------------------------

    if '~' in path_to_si_reader:
	    path_to_si_reader = path_to_si_reader.replace('~', home)
    print path_to_si_reader
    sys.path.append(path_to_si_reader)
    from ScanImageTiffReader import ScanImageTiffReader

    #acquisition_dir = os.path.join(source, experiment, session, acquisition)
    acquisition_dir = os.path.join(source, animalid, session, acquisition)

    rawtiffs = os.listdir(os.path.join(acquisition_dir, run, 'raw'))
    rawtiffs = [t for t in rawtiffs if t.endswith('.tif')]
    print rawtiffs

    scanimage_metadata = dict()
    scanimage_metadata['filenames'] = []
    scanimage_metadata['session'] = session
    scanimage_metadata['acquisition'] = acquisition
    #scanimage_metadata['experiment'] = experiment 
    scanimage_metadata['run'] = run

    for fidx,rawtiff in enumerate(sorted(rawtiffs, key=natural_keys)):
	
        curr_file = 'File{:03d}'.format(fidx+1)
        print "Processing:", curr_file
        
        currtiffpath = os.path.join(acquisition_dir, run, 'raw', rawtiff)
            
        # Make sure TIFF is READ ONLY:
        os.chmod(currtiffpath, S_IREAD|S_IRGRP|S_IROTH)  
        
        scanimage_metadata[curr_file] = {'SI': None}

        metadata = ScanImageTiffReader(currtiffpath).metadata()
        meta = metadata.splitlines()
        del metadata

        # descs = ScanImageTiffReader(os.path.join(acquisition_dir, rawtiff)).descriptions()
        # vol=ScanImageTiffReader("my.tif").data();

        # Get ScanImage metadata:
        SI = [l for l in meta if 'SI.' in l]
        del meta

        # Iterate through list of SI. strings and turn into dict:
        SI_struct = {}
        for item in SI:
            t = SI_struct
            fieldname = item.split(' = ')[0] #print fieldname
            value = item.split(' = ')[1]
            num_format = re.compile(r'\-?[0-9]+\.?[0-9]*|\.?[0-9]')
            sci_format = re.compile('-?\ *[0-9]+\.?[0-9]*(?:[Ee]\ *-?\ *[0-9]+)?')
            if "'" in item:
                value = str(value) 
            #elif len(re.findall(sci_format, value))>0:
            #    value = float(value)
            #elif any(c.isalpha() for c in value):
            #    value = str(value)   
            elif len(re.findall(num_format, value))>0:  # has numbers 
                if value.isdigit():
                    value = int(value)
                elif '[' in value:
                    ends = [value.index('[')+1,  value.index(']')]
                    tmpvalue = value[ends[0]:ends[1]]
                    if ';' in value:
                        rows = tmpvalue.split(';'); 
                        value = [[float(i) for i in re.findall(num_format, row)] for row in rows]
                    else:
                        value = [float(i) for i in re.findall(num_format, tmpvalue)]                    
            for ix,part in enumerate(fieldname.split('.')):
                nsubfields = len(fieldname.split('.'))
                if ix==nsubfields-1:
                    t.setdefault(part, value)
                else:
                    t = t.setdefault(part, {})
        
        # print SI_struct.keys()
        scanimage_metadata['filenames'].append(rawtiff)
        scanimage_metadata[curr_file]['SI'] = SI_struct['SI']

        # Save dict:
        raw_simeta_json = '%s.json' % raw_simeta_basename
        with open(os.path.join(acquisition_dir, run, 'raw', raw_simeta_json), 'w') as fp:
            json.dump(scanimage_metadata, fp, sort_keys=True, indent=4)


        # Also save as .mat for now:
        #raw_simeta_mat = '%s.mat' % raw_simeta_basename
        #scipy.io.savemat(os.path.join(acquisition_dir, raw_simeta_mat), mdict=scanimage_metadata, long_field_names=True)
        #print "Saved .MAT to: ", os.path.join(acquisition_dir, raw_simeta_mat)


        # Create REFERENCE info file or overwrite relevant fields, if exists: 
        refinfo_json = '%s.json' % reference_info_basename
        if new_acquisition is True:
            refinfo = dict()
        elif os.path.exists(os.path.join(acquisition_dir, run, refinfo_json)):
            with open(os.path.join(acquisition_dir, run, refinfo_json), 'r') as fp:
		        refinfo = json.load(fp)
        else:
            refinfo = dict() 

        refinfo['source'] = source
        refinfo['animal_id'] = animalid #experiment
        refinfo['session'] = session
        refinfo['acquisition'] = acquisition
        refinfo['run'] = run #functional_dir
        specified_nslices =  int(scanimage_metadata['File001']['SI']['hStackManager']['numSlices'])
        refinfo['slices'] = range(1, specified_nslices+1) 
        refinfo['ntiffs'] = len(rawtiffs)
        if isinstance(scanimage_metadata['File001']['SI']['hChannels']['channelSave'], int):
            refinfo['nchannels'] =  scanimage_metadata['File001']['SI']['hChannels']['channelSave']
        else:
            refinfo['nchannels'] = len(scanimage_metadata['File001']['SI']['hChannels']['channelSave']) # if i.isdigit()])
        refinfo['nvolumes'] = int(scanimage_metadata['File001']['SI']['hFastZ']['numVolumes'])
        refinfo['lines_per_frame'] = int(scanimage_metadata['File001']['SI']['hRoiManager']['linesPerFrame'])
        refinfo['pixels_per_line'] = int(scanimage_metadata['File001']['SI']['hRoiManager']['pixelsPerLine'])
        refinfo['raw_simeta_path'] = os.path.join(acquisition_dir, run, 'raw', raw_simeta_json) #raw_simeta_mat)

        if 'acquisition_base_dir' not in refinfo.keys():
            refinfo['acquisition_base_dir'] = acquisition_dir
        if 'mcparams_path' not in refinfo.keys():
            # TODO:  Don't make this specifically tied to MAT
            refinfo['mcparams_path'] = os.path.join(acquisition_dir, run, 'processed', 'mcparams.mat')
        if 'roi_dir' not in refinfo.keys():
            refinfo['roi_dir'] = os.path.join(acquisition_dir, 'ROIs')
        if 'trace_dir' not in refinfo.keys():
            refinfo['trace_dir'] = os.path.join(acquisition_dir, 'Traces')

        with open(os.path.join(acquisition_dir, run, refinfo_json), 'w') as fp:
            json.dump(refinfo, fp, indent=4)
        
        #refinfo_mat = '%s.mat' % reference_info_basename
        #scipy.io.savemat(os.path.join(acquisition_dir, refinfo_mat), mdict=refinfo)


if __name__ == '__main__':
    main(sys.argv[1:]) 
