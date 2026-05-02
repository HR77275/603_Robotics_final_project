import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class ObjectTriggerStub(Node):
    """Explicitly labeled placeholder for Soumik's object-trigger lane."""

    def __init__(self) -> None:
        super().__init__("object_trigger_stub")
        self.declare_parameter("enabled", False)
        self.declare_parameter("topic", "/object_trigger")
        self.declare_parameter("trigger_label", "clipboard")
        self.declare_parameter("period_sec", 2.0)

        topic = self.get_parameter("topic").value
        period = float(self.get_parameter("period_sec").value)
        self.publisher = self.create_publisher(String, topic, 10)
        self.timer = self.create_timer(period, self._on_timer)
        self.get_logger().info("Object trigger stub loaded; enabled=false means it will publish nothing.")

    def _on_timer(self) -> None:
        if not bool(self.get_parameter("enabled").value):
            return

        label = str(self.get_parameter("trigger_label").value).strip() or "object"
        msg = String()
        msg.data = f"TRIGGER_OBJECT_DETECTED:{label}"
        self.publisher.publish(msg)
        self.get_logger().info(f"stub object trigger published for {label!r}")


def main(args=None) -> None:
    rclpy.init(args=args)
    node = ObjectTriggerStub()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
