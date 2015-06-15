from setuptools import setup, find_packages

setup(
    name="parspective",
    version="0.0.0",
    packages=find_packages(),

    # Metadata for PyPi
    url="https://github.com/project-rig/parspective",
    author="Jonathan Heathcote",
    description="A tool for generating diagrams of SpiNNaker Place & Route solutions",
    license="GPLv2",
    keywords="spinnaker placement routing diagram cairo",

    # Requirements
    install_requires=["rig >=0.5.0", "six", "enum34", "cairocffi"],
    
    # Scripts
    entry_points={
        "console_scripts": [
            "parspective = parspective.cli:main",
        ],
    },
)
