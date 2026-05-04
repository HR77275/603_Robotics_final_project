import math

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image

from robomaster_perception_msgs.msg import PeopleDepth, PersonDepth


class FakePerception(Node):
    def __init__(self):
        super().__init__('fake_perception')

        self.depth_pub = self.create_publisher(PeopleDepth, '/people/depth', 10)
        self.image_pub = self.create_publisher(Image, '/perception/tracking_debug_image', 10)

        self.t = 0.0
        self.timer = self.create_timer(0.05, self.loop)

        self.get_logger().info('Fake perception publishing /people/depth and /perception/tracking_debug_image')

    def loop(self):
        self.t += 0.05

        depth = 2.0 + 0.8 * math.sin(self.t * 0.6)
        x_center = 0.5 + 0.23 * math.sin(self.t * 0.8)

        people = PeopleDepth()
        people.header.stamp = self.get_clock().now().to_msg()
        people.header.frame_id = 'camera_optical_link'

        person = PersonDepth()
        person.track_id = 1
        person.roi.x_offset = float(x_center)
        person.roi.y_offset = 0.5
        person.roi.width = 0.25
        person.roi.height = 0.55
        person.depth_m = float(depth)
        person.raw_depth_m = float(depth)
        person.tof_range_m = float(depth)
        person.tof_scale = 1.0
        person.tof_used = False
        person.confidence = 1.0
        person.method = 'fake'
        people.people.append(person)
        self.depth_pub.publish(people)

        image = Image()
        image.header = people.header
        image.height = 480
        image.width = 640
        image.encoding = 'rgb8'
        image.is_bigendian = False
        image.step = image.width * 3
        image.data = bytes(image.height * image.step)
        self.image_pub.publish(image)


def main(args=None):
    rclpy.init(args=args)
    node = FakePerception()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
