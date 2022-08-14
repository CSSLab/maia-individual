from setuptools import setup, find_packages
import re

with open('backend/__init__.py') as f:
    versionString = re.search(r"__version__ = '(.+)'", f.read()).group(1)

if __name__ == '__main__':
    setup(name='backend',
        version = versionString,
        author="Anon",
        author_email="anon@anon",
        packages = find_packages(),
        install_requires = [
                'numpy',
                'matplotlib',
                'pandas',
                'seaborn',
                'python-chess>=0.30.0',
                'pytz',
                'natsort',
                'humanize',
                'pyyaml',
                'tensorboardX',
        ],
    )
