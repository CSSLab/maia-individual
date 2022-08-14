##!/bin/bash
set -e

vals_dat_dir="../../data/transfer_players_data/validate_metadata/"
vals_dir="../../data/transfer_players_validate"
output_dir="../../data/transfer_players_extended"
list_file='../../data/extended_list.csv'

num_per_bin=5
bins="1100 1300 1500 1700 1900"


python3 select_binned_players.py $vals_dat_dir $list_file $num_per_bin $bins

mkdir -p $output_dir

while read player; do
    echo $player
    cp -r ${vals_dir}/${player} ${output_dir}
done < $list_file
