from glob import glob
from setuptools import find_packages, setup

package_name = "cs603_voice_intent"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
        (f"share/{package_name}/launch", glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="CS603 Team",
    maintainer_email="soumikbhatta@example.com",
    description="Voice intent publisher and safe demo bridge for the CS603 RoboMaster final project.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "voice_intent_node = cs603_voice_intent.voice_intent_node:main",
            "voice_cmd_vel_bridge = cs603_voice_intent.voice_cmd_vel_bridge:main",
            "object_trigger_stub = cs603_voice_intent.object_trigger_stub:main",
            "behavior_fsm = cs603_voice_intent.behavior_fsm:main",
        ],
    },
)
