#!/bin/bash

train_frac=80
val_frac=10
test_frac=10

input_files="/maiadata/transfer_players_data/test"
output_files="/maiadata/transfer_players_test"
mkdir -p $output_files

for player_file in $input_files/*.bz2; do
    f=${player_file##*/}
    p_name=${f%.pgn.bz2}
    p_dir=$output_files/$p_name
    split_dir=$output_files/$p_name/split
    mkdir -p $p_dir
    mkdir -p $split_dir
    echo $p_name $p_dir
    python split_by_player.py $player_file $p_name $split_dir/games


    for c in "white" "black"; do
        python pgn_fractional_split.py $split_dir/games_$c.pgn.bz2 $split_dir/train_$c.pgn.bz2 $split_dir/validate_$c.pgn.bz2 $split_dir/test_$c.pgn.bz2 --ratios $train_frac $val_frac $test_frac

        cd $p_dir
        mkdir -p pgns
        for s in "train" "validate" "test"; do
            mkdir -p $s
            mkdir $s/$c

            #using tool from:
            #https://www.cs.kent.ac.uk/people/staff/djb/pgn-extract/
            bzcat $split_dir/${s}_${c}.pgn.bz2 | pgn-extract -7 -C -N  -#1000

            cat *.pgn > pgns/${s}_${c}.pgn
            rm -v *.pgn

             #using tool from:
            #https://github.com/DanielUranga/trainingdata-tool
            screen -S "${p_name}-${c}-${s}" -dm bash -c "cd ${s}/${c}; trainingdata-tool -v ../../pgns/${s}_${c}.pgn"
        done
        cd -
    done
    while [ `screen -ls | wc -l` -gt 20 ]; do
        printf "waiting\r"
        sleep 10
    done

done
