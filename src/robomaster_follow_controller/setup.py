from glob import glob
from setuptools import find_packages, setup

package_name = 'robomaster_follow_controller'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='humble_ros2',
    maintainer_email='humble_ros2@example.com',
    description='RoboMaster person following controller using perception depth and tracked image output.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'follow_node = robomaster_follow_controller.follow_node:main',
            'fake_perception = robomaster_follow_controller.fake_perception:main',
        ],
    },
)
