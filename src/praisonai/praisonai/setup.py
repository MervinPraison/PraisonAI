from setuptools import setup
from setuptools.command.install import install
import subprocess
import sys

class PostInstallCommand(install):
    def run(self):
        install.run(self)
        # Install Playwright browsers
        subprocess.check_call([sys.executable, '-m', 'playwright', 'install'])

setup(
    cmdclass={
        'install': PostInstallCommand,
    }
) 