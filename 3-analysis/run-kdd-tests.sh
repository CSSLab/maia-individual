#!/bin/bash

mkdir -p ../data
mkdir -p ../data/kdd_sweeps

screen -S "kdd-sweep" -dm bash -c "source ~/.bashrc; python3 ../../analysis/move_prediction_csv.py ../../transfer_models ../../datasets/10000_full_2019-12.csv.bz2 ../data/kdd_sweeps"
