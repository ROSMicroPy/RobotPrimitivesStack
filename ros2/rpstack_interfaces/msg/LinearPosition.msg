# Header stamp is gateway receipt time, not device measurement time.
# frame_id identifies the coordinate frame; the gateway does not transform values.
std_msgs/Header header
float64 position_m
bool valid
# Quality is the provider's declared value, not an estimated accuracy guarantee.
float64 quality
# Original device timestamp, on its own clock. Never interpret as ROS time.
bool source_timestamp_valid
uint64 source_timestamp_ns
