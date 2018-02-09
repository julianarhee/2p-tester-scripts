#!/bin/bash
ANIMALID="$1"
SESSION="$2"
RIDHASH="$3"
RIDPATH="/n/coxfs01/2p-data/${ANIMALID}/${SESSION}/ROIs/tmp_rids"
#echo $RIDPATH
echo "Requested single ROI ID to memmap - ${RIDHASH}."

if [ "$#" == 5 ]; then
    FIRSTTIFF="$4"
    LASTTIFF="$5"
else
    FIRSTTIFF=1
    if [ "$#" == 4 ]; then
        LASTTIFF="$4"
    else
        LASTTIFF=1
    fi
fi
echo "NMF-ROI extraction from File ${FIRSTTIFF} to ${LASTTIFF}."

#if [ "$#" -gt 3 ]; then
#    NTIFFS="$4"
#    echo "Requesting NMF extraction on ${NTIFFS} tiff files."
#else
#    NTIFFS=1
#fi
#echo "N tiffs: ${NTIFFS}"
#
FILES=($RIDPATH/*$RIDHASH.json)

# get size of array
NUMFILES=${#FILES[@]}

# subtract 1 for 0-indexing
ZBNUMFILES=$(($NUMFILES - 1))

if [ $ZBNUMFILES == 0 ]; then
    PARAMSPATH=${FILES[0]}
    echo "Params path: $PARAMSPATH"
 
    export PARAMSPATH RIDHASH

    # submit to slurm
    sbatch --array=1-${LASTTIFF} /n/coxfs01/2p-pipeline/repos/2p-pipeline/pipeline/python/slurm/nmf_tiff_array.sbatch

fi

