ARG ROS_BASE_IMAGE=bj-warehouse.tencentcloudcr.com/phanthy-motus/ros-base:latest
FROM ${ROS_BASE_IMAGE}
ARG DEBIAN_FRONTEND=noninteractive
RUN if ! command -v colcon >/dev/null || ! dpkg -s ros-humble-rosidl-default-generators ros-humble-nav-msgs ros-humble-rmw-fastrtps-cpp python3-yaml >/dev/null 2>&1; then \
      apt-get update && apt-get install -y --no-install-recommends python3-colcon-common-extensions python3-yaml ros-humble-rosidl-default-generators ros-humble-nav-msgs ros-humble-sensor-msgs ros-humble-rmw-fastrtps-cpp && rm -rf /var/lib/apt/lists/*; \
    fi
WORKDIR /q1_ws
ADD aimdk_msgs-618d995d.tar.gz src/
RUN . /opt/ros/humble/setup.sh && MAKEFLAGS=-j3 colcon build --packages-select aimdk_msgs --cmake-args -DBUILD_TESTING=OFF && rm -rf build log
WORKDIR /work
COPY common/ common/
COPY main.py status.py robot.py config.yaml primebot/q1/
ENV PYTHONPATH=/work PYTHONUNBUFFERED=1 RMW_IMPLEMENTATION=rmw_fastrtps_cpp
EXPOSE 15748
ENTRYPOINT []
CMD ["/bin/bash", "-c", "source /opt/ros/humble/setup.bash && source /q1_ws/install/setup.bash && exec /usr/bin/python3 /work/primebot/q1/main.py"]
