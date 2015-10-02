from setuptools import setup, find_packages

setup(
    name="rig-par-diagram",
    version="0.0.3",
    packages=find_packages(),

    # Metadata for PyPi
    url="https://github.com/project-rig/rig-par-diagram",
    author="Jonathan Heathcote",
    description="A tool for generating diagrams of SpiNNaker Place & Route solutions",
    license="GPLv2",
    keywords="spinnaker placement routing diagram cairo",

    # Requirements
    install_requires=["rig >=0.5.0", "six", "enum34", "cairocffi"],
    
    # Scripts
    entry_points={
        "console_scripts": [
            "rig-par-diagram = rig_par_diagram.cli:main",
        ],
    },
)
