cmake_minimum_required(VERSION 3.8)
project(robomaster_perception_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(std_msgs REQUIRED)
find_package(robomaster_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/TrackedPerson.msg"
  "msg/TrackedPeople.msg"
  "msg/PersonDepth.msg"
  "msg/PeopleDepth.msg"
  "msg/PersonIdentity.msg"
  "msg/PeopleIdentities.msg"
  DEPENDENCIES std_msgs robomaster_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()
