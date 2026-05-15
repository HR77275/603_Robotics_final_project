from glob import glob
from setuptools import find_packages, setup

package_name = 'robomaster_perception'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(),
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
    description='RoboMaster perception and tracking nodes.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'detection_tracker_node = robomaster_perception.detection_tracker_node:main',
            'deepsort_tracker_node = robomaster_perception.deepsort_tracker_node:main',
            'depth_estimator_node = robomaster_perception.depth_estimator_node:main',
            'tracking_overlay_node = robomaster_perception.tracking_overlay_node:main',
            'enroll_faces = robomaster_perception.enroll_faces:main',
            'face_identity_node = robomaster_perception.face_identity_node:main',
        ],
    },
)
