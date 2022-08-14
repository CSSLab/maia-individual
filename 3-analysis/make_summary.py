import argparse
import os
import os.path
import json
import re
import glob

import pandas
import numpy as np

root_dir = os.path.relpath("../..", start=os.path.dirname(os.path.abspath(__file__)))
root_dir = os.path.abspath(root_dir)
cats_ply = {
        'early' : (0, 10),
        'mid' : (11, 50),
        'late' : (51, 999),
        'kdd' : (11, 999),
    }

last_n = [2**n for n in range(12)]

def main():
    parser = argparse.ArgumentParser(description='Create summary json from results csv', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('input', help='input CSV')
    parser.add_argument('output', help='output JSON')
    parser.add_argument('--players_infos', default="/ada/projects/chess/backend-backend/data/players_infos.json")#os.path.join(root_dir, 'data/players_infos.json'))
    args = parser.parse_args()

    with open(args.players_infos) as f:
        player_to_dat = json.load(f)

    fixed_data_paths = glob.glob("/ada/projects/chess/backend-backend/data/top_2000_player_data/*.csv.bz2")
    fixed_data_lookup = {p.split('/')[-1].replace('.csv.bz2','') :p for p in fixed_data_paths}


    df = collect_results_csv(args.input ,player_to_dat, fixed_data_lookup)

    r_d = dict(df.iloc[0])
    sum_dict = {
        'count' : len(df),
        'player' : r_d['player_name'],
        'model' : r_d['model_name'],
        'backend' : bool(r_d['backend']),
        #'model_correct' : float(df['model_correct'].mean()),
        'elo' : r_d['elo'],
    }
    c = 'white' if 'white' in args.input.split('/')[-1].split('_')[-1] else 'black'

    add_infos(sum_dict, "full", df)

    try:
        csv_raw_path = glob.glob(f"/ada/projects/chess/backend-backend/data/transfer_players_*/{r_d['player_name']}/csvs/test_{c}.csv.bz2")[0]
    except IndexError:
        if args.input.endswith('kdd.csv.bz2'):
            csv_raw_path = "/ada/projects/chess/backend-backend/data/reduced_kdd_test_set.csv.bz2"
        else:
            csv_raw_path = None
    if csv_raw_path is not None:
        csv_base = pandas.read_csv(csv_raw_path, index_col=['game_id', 'move_ply'], low_memory=False)
        csv_base['winrate_no_0'] = np.where(csv_base.reset_index()['move_ply'] < 2,np.nan, csv_base['winrate'])
        csv_base['next_wr'] = 1 - csv_base['winrate_no_0'].shift(-1)
        csv_base['move_delta_wr'] = csv_base['next_wr'] - csv_base['winrate']
        csv_base_dropped = csv_base[~csv_base['winrate_loss'].isna()]
        csv_base_dropped = csv_base_dropped.join(df.set_index(['game_id', 'move_ply']), how = 'inner', lsuffix = 'r_')
        csv_base_dropped['move_delta_wr_rounded'] = (csv_base_dropped['move_delta_wr'] * 1).round(2) / 1

        for dr in csv_base_dropped['move_delta_wr_rounded'].unique():
            if dr < 0 and dr >-.32:
                df_dr = csv_base_dropped[csv_base_dropped['move_delta_wr_rounded'] == dr]
                add_infos(sum_dict, f"delta_wr_{dr}", df_dr)

    for k, v in player_to_dat[r_d['player_name']].items():
        if k != 'name':
            sum_dict[k] = v
    if r_d['backend']:
        sum_dict['backend_elo'] = int(r_d['model_name'].split('_')[-1])


    for c, (p_min, p_max) in cats_ply.items():
        df_c = df[(df['move_ply'] >= p_min) & (df['move_ply'] <= p_max)]
        add_infos(sum_dict, c, df_c)

    for year in df['UTCDate'].dt.year.unique():
        df_y = df[df['UTCDate'].dt.year == year]
        add_infos(sum_dict, int(year), df_y)

    for ply in range(50):
        df_p = df[df['move_ply'] == ply]
        if len(df_p) > 0:
            # ignore the 50% missing ones
            add_infos(sum_dict, f"ply_{ply}", df_p)

    for won in [True, False]:
        df_w = df[df['won'] == won]
        add_infos(sum_dict, "won" if won else "lost", df_w)

    games = list(df.groupby('game_id').first().sort_values('UTCDate').index)

    for n in last_n:
        df_n = df[df['game_id'].isin(games[-n:])]
        add_infos(sum_dict, f"last_{n}", df_n)

        p_min, p_max = cats_ply['kdd']
        df_n_kdd = df_n[(df_n['move_ply'] >= p_min) & (df_n['move_ply'] <= p_max)]
        add_infos(sum_dict, f"last_{n}_kdd", df_n_kdd)

    with open(args.output, 'wt') as f:
        json.dump(sum_dict, f)

def collect_results_csv(path, player_to_dat, fixed_data_lookup):
    try:
        df = pandas.read_csv(path, low_memory=False)
    except EOFError:
        print(f"Error on: {path}")
        return None
    if len(df) < 1:
        return None
    df['colour'] = re.search("(black|white)\.csv\.bz2", path).group(1)
    #df['class'] = re.search(f"{base_dir}/([a-z]*)/", path).group(1)
    backend = 'final_backend_' in df['model_name'].iloc[0]
    df['backend'] = backend
    try:
        df['player'] = df['player_name']
    except KeyError:
        pass
    try:
        if backend:
            df['model_type'] = df['model_name'].iloc[0].replace('final_', '')
        else:
            df['model_type'] = df['model_name'].iloc[0].replace(f'{df.iloc[0]["player"]}_', '')
        for k, v in player_to_dat[df.iloc[0]["player"]].items():
            if k != 'name':
                df[k] = v
        games_df = pandas.read_csv(fixed_data_lookup[df['player'].iloc[0]],
                                   low_memory=False, parse_dates = ['UTCDate'], index_col = 'game_id')
        df = df.join(games_df, how= 'left', on = 'game_id', rsuffix='_per_game')
    except Exception as e:
        print(f"{e} : {path}")
        raise
    return df

def add_infos(target_dict, name, df_sub):
    target_dict[f'model_correct_{name}'] = float(df_sub['model_correct'].dropna().mean())
    target_dict[f'model_correct_per_game_{name}'] = float(df_sub.groupby(['game_id']).mean()['model_correct'].dropna().mean())
    target_dict[f'count_{name}'] = len(df_sub)
    target_dict[f'std_{name}'] = float(df_sub['model_correct'].dropna().std())
    target_dict[f'num_games_{name}'] = len(df_sub.groupby('game_id').count())

if __name__ == "__main__":
    main()
