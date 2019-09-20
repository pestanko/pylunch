import io
import re
from pathlib import Path

from setuptools import find_packages, setup

with io.open('pylunch/__init__.py', 'rt', encoding='utf8') as f:
    VERSION = re.search(r'__version__ = \'(.*?)\'', f.read()).group(1)

long_description = Path('README.md').read_text(encoding='utf-8')

requirements = ['pyyaml', 
                'click', 
                'requests', 
                'coloredlogs', 
                'python-Levenshtein', 
                'fuzzywuzzy', 
                'html2text', 
                'beautifulsoup4', 
                'lxml',
                'pyzomato',
                'pdfminer-six',
                'ipython',
                'flask',
                'flask-jwt-extended',
                'werkzeug',
                'pytesseract',
                'pillow',
                ]
                
entry_points = {'console_scripts': ['pylunch = pylunch.cli:main_cli', ]}
extra_requirements = {
    'dev': ['pytest>=3', 'coverage' ],
    'docs': ['sphinx', ]
}

setup(name='pylunch',
      version=VERSION,
      description='Internal pylunch cli tool to get lunch info',
      author='Peter Stanko',
      author_email='peter.stanko0@gmail.com',
      url='https://gitlab.com/pestanko/pylunch',
      packages=find_packages(exclude=("tests",)),
      long_description=long_description,
      long_description_content_type='text/markdown',
      include_package_data=True,
      install_requires=requirements,
      extras_require=extra_requirements,
      entry_points=entry_points,
      classifiers=[
          "Programming Language :: Python :: 3",
          'Programming Language :: Python :: 3.7',
          "Operating System :: OS Independent",
          "License :: OSI Approved :: Apache Software License",
          'Intended Audience :: Developers',
          'Topic :: Utilities',
      ], )
