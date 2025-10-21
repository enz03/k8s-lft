# unified setup.py for profissa_lft and k8s_lft
from setuptools import setup, find_packages
from setuptools.command.install import install
import subprocess

class CustomInstall(install):
    def run(self):
        subprocess.run("chmod +x dependencies.sh", shell=True)
        subprocess.run("sudo ./dependencies.sh", shell=True)
        install.run(self)

setup(
    name='lft',
    version='1.1.0',
    packages=find_packages(),  # detecta todos os pacotes: profissa_lft e k8s_lft
    install_requires=[
        'pandas',
        'kubernetes'
    ],
    author='Alexandre Mitsuru Kaihara & Enzo Zanetti Celentano',
    author_email='alexandreamk1@gmail.com',
    description='LFT: lightweight network topologies emulation with Docker or Kubernetes',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    url='https://github.com/alexandrekaihara/lft',
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.9',
    cmdclass={
        'install': CustomInstall
    },
    include_package_data=True
)
