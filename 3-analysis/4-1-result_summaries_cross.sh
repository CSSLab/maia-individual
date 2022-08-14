#!/bin/bash
set -e

max_screens=80

targets_dir="../../data/transfer_results_cross"
outputs_dir="../../data/transfer_results_cross_summaries"
mkdir -p outputs_dir

for p in $targets_dir/*/*.bz2; do
    #result=$(echo "$p" | sed "s/$targets_dir/$outputs_dir/g")
    out_path=${p/$targets_dir/$outputs_dir}
    out_path=${out_path/.csv.bz2/.json}
    base=`dirname ${p/$targets_dir/}`
    base=${base//\//-}
    mkdir -p `dirname $out_path`
    echo $base
    #"${${}/${outputs_dir}/${targets_dir}}"
    screen -S "summary${base}" -dm bash -c "source ~/.bashrc; python3 make_summary.py ${p} ${out_path}"
    while [ `screen -ls | wc -l` -gt $max_screens ]; do
        printf "waiting\r"
        sleep 10
    done
done



