#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Fri Feb  2 15:09:36 2018

@author: julianarhee
"""

import os
import sys
import logging
import shutil
from pipeline.python.evaluation.evaluate_roi_extraction import run_rid_eval

def main():

    rid_path = sys.argv[1]
    nproc = sys.argv[2]
    print "Received %i args in." % len(sys.argv)
    if len(sys.argv) == 4:
        snr = float(sys.argv[3])
    else:
        snr = 2.0
    if len(sys.argv) == 5:
        rcorr = float(sys.argv[4])
    else:
        rcorr = 0.8

    #cluster_backend = sys.argv[3]
    if len(nproc) == 0:
        nproc = 12
    else:
        nproc = int(nproc)

#    if len(cluster_backend) == 0:
#        cluster_backend = 'local'
#
    roi_hash = os.path.splitext(os.path.split(rid_path)[-1])[0].split('_')[-1]
    logdir = os.path.join(os.path.split(rid_path)[0], 'logging_%s' % roi_hash)
    if not os.path.exists(logdir):
        os.makedirs(logdir)
    print "Logging to dir: %s" % logdir
    #print "Cluster backend: %s" % cluster_backend
    
    # Make sure TMP RID file is in 'completed' dir:
    if 'completed' not in rid_path:
        completed_dir = os.path.join(os.path.split(rid_path)[0], 'completed')
        if not os.path.exists(completed_dir):
            os.makedirs(completed_dir)
        tmp_rid_dir = os.path.split(rid_path)[0]
        rid_fn = os.path.split(rid_path)[-1]
        if os.path.exists(rid_path):
            print "Moving completed tmp file to proper dir."
            shutil.move(os.path.join(tmp_rid_dir, rid_fn), os.path.join(completed_dir, rid_fn))
            print "Evaluating ROI file at: %s" % os.path.join(completed_dir, rid_fn)
    
    logging.basicConfig(level=logging.DEBUG, filename="%s/logfile_%s_roieval" % (logdir, roi_hash), filemode="a+",
                        format="%(asctime)-15s %(levelname)-8s %(message)s")

    logging.info("RID %s -- starting ROI EVAL ..." % roi_hash)
    logging.info(rid_path)
   
    eval_filepath = run_rid_eval(rid_path, nprocs=nproc, cluster_backend='local', rootdir='/n/coxfs01/2p-data', min_SNR=snr, rval_thr=rcorr)
    
    logging.info("FINISHED evaluating ROIs from RID:\n%s" % roi_hash)
    logging.info("Saved eval results to: %s" % eval_filepath)

if __name__=="__main__":

    main()
