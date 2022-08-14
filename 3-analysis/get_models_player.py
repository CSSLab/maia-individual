import argparse
import os
import os.path
import yaml

import pandas

def main():
    parser = argparse.ArgumentParser(description='Quick helper for getting model players', formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('input', help='input model dir')
    args = parser.parse_args()

    conf_path = os.path.abspath(os.path.join(args.input, "config.yaml"))
    if os.path.isfile(conf_path):
        with open(conf_path) as f:
            cfg = yaml.safe_load(f)
        try:
            print(cfg['full_config']['name'])
        except (KeyError, TypeError):
            #some have corrupted configs
            if 'Eron_Capivara' in args.input:
                print('Eron_Capivara') #hack
            else:

                print(os.path.basename(os.path.dirname(conf_path)).split('_')[0])
    else:
        raise FileNotFoundError(f"Not a config path: {conf_path}")

if __name__ == "__main__":
    main()
