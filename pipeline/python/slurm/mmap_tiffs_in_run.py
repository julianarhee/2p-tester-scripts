#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Jan 31 16:49:35 2018

@author: julianarhee
"""

import os
import sys
import logging
from pipeline.python.rois.caiman2D import mmap_tiffs

def main(pid_filepath):
    
    logging.info(pid_filepath)
    
    mmap_paths = mmap_tiffs(pid_filepath)
    
    logging.info("FINISHED memmapping tiffs from RID:\n%s" % pid_filepath)
    logging.info("Created %i .mmap files." % len(mmap_paths))
    

if __name__=="__main__":
    
    pid_path = sys.argv[1]
    roi_hash = os.path.splitext(os.path.split(pid_path)[-1])[0].split('_')[-1]

    logging.basicConfig(level=logging.DEBUG, filename="logfile_%s_memmap" % roi_hash, filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")
    
    logging.info("RID %s -- starting memmapping ..." % roi_hash)
    
    main(pid_path)
    
    logging.info("RID %s -- memmapping done!" % roi_hash)