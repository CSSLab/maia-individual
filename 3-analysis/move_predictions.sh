#!/bin/bash
set -e

data_dir="../../data/transfer_players_train"
outputs_dir="../../data/transfer_players_train_results/weights_testing"
maia_path="../../models/maia/1900"
models_path="../models/weights_testing"

kdd_path="../../datasets/10000_full_2019-12.csv.bz2"

mkdir -p $outputs_dir

for player_dir in $data_dir/*; do
    player_name=`basename ${player_dir}`
    echo $player_name
    mkdir -p $outputs_dir/$player_name

    for c in "white" "black"; do
        #echo "source ~/.bashrc; python3 prediction_generator.py --target_player ${player_name} ${models_path}/${player_name}*/ ${data_dir}/${player_name}/csvs/test_${c}.csv.bz2 $outputs_dir/${player_name}/transfer_test_${c}.csv.bz2"
        screen -S "test-transfer-${c}-${player_name}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player_name} ${models_path}/${player_name}*/ ${data_dir}/${player_name}/csvs/test_${c}.csv.bz2 $outputs_dir/${player_name}/transfer_test_${c}.csv.bz2"
        screen -S "test-maia-${c}-${player_name}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py --target_player ${player_name} ${maia_path} ${data_dir}/${player_name}/csvs/test_${c}.csv.bz2 $outputs_dir/$player_name/maia_test_${c}.csv.bz2"
    done
    screen -S "kdd-transfer-${player_name}" -dm bash -c "source ~/.bashrc; python3 prediction_generator.py ${models_path}/${player_name}*/ ${kdd_path} $outputs_dir/$player_name/transfer_kdd.csv.bz2"

    while [ `screen -ls | wc -l` -gt 250 ]; do
        printf "waiting\r"
        sleep 10
    done
done
