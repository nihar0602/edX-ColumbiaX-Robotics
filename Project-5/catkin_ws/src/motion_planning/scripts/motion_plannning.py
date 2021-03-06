#!/usr/bin/env python

"""
This is a skeleton code.
"""

from copy import deepcopy
import math
import numpy
import random
from threading import Thread, Lock
import sys

import actionlib
import control_msgs.msg
import geometry_msgs.msg
import moveit_commander
import moveit_msgs.msg
import moveit_msgs.srv
import rospy
import sensor_msgs.msg
import tf
import trajectory_msgs.msg

def convert_to_message(T):
    t = geometry_msgs.msg.Pose()
    position = tf.transformations.translation_from_matrix(T)
    orientation = tf.transformations.quaternion_from_matrix(T)
    t.position.x = position[0]
    t.position.y = position[1]
    t.position.z = position[2]
    t.orientation.x = orientation[0]
    t.orientation.y = orientation[1]
    t.orientation.z = orientation[2]
    t.orientation.w = orientation[3]        
    return t

def convert_from_message(msg):
    R = tf.transformations.quaternion_matrix((msg.orientation.x,
                                              msg.orientation.y,
                                              msg.orientation.z,
                                              msg.orientation.w))
    T = tf.transformations.translation_matrix((msg.position.x, 
                                               msg.position.y, 
                                               msg.position.z))
    return numpy.dot(T,R)

def convert_from_trans_message(msg):
    R = tf.transformations.quaternion_matrix((msg.rotation.x,
                                              msg.rotation.y,
                                              msg.rotation.z,
                                              msg.rotation.w))
    T = tf.transformations.translation_matrix((msg.translation.x, 
                                               msg.translation.y, 
                                               msg.translation.z))
    return numpy.dot(T,R)
   
class RRT_Node:
    def __init__(self, joint_val, parent=None):
        # Variable
        self.state = joint_val
        self.parent = parent


class RRTSearchTree:
    def __init__(self, init):
        self.root = init
        self.nodes = [self.root]

    def find_nearest(self, query):
        min_dist = 1000000
        nearest_node = self.root
        for n_i in self.nodes:
            dist = numpy.linalg.norm(query - n_i.state)
            if dist < min_dist:
                nearest_node = n_i
                min_dist = dist
        return nearest_node, min_dist

    def add_node(self, node):
        self.nodes.append(node)

    # Return list of lists
    def get_back_path(self, node):
        path = []
        while node.parent is not None:
            path.append(node.state)
            node = node.parent
        # root node
        path.append(node.state)
        path.reverse()
        return path


class RRT:
    def __init__(self, num_samples, no_joints, step_length=0.5, limits=None):
        # number of samples for time out
        self.K = num_samples
        # number of joint
        self.n = no_joints
        # step size to move in the direction of random configuration
        self.epsilon = step_length
        # limits set the lower and upper bound for the random config generation
        # self.limits = limits
        self.found_path = False

    def sample(self, q_min, q_max):
        new_config = [random.randrange(q_min, q_max) for _ in range(self.n)]
        return numpy.array(new_config)

    def extend(self, q):
        (nearest_node, distance) = self.T.find_nearest(q)

    def new_config_generator(self, nn_jointVal, random_sample, distance):
        if distance < self.epsilon:
            return random_sample
        else:
            new_config = nn_jointVal + self.epsilon * ((random_sample - nn_jointVal) / distance)
            return new_config
   

class MoveArm(object):

    def __init__(self):
        print "Motion Planning Initializing..."
        # Prepare the mutex for synchronization
        self.mutex = Lock()

        # Some info and conventions about the robot that we hard-code in here
        # min and max joint values are not read in Python urdf, so we must hard-code them here
        self.num_joints = 7
        self.q_min = []
        self.q_max = []
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        self.q_min.append(-3.1459);self.q_max.append(3.1459)
        # How finely to sample each joint
        self.q_sample = [0.05, 0.05, 0.05, 0.1, 0.1, 0.1, 0.1]
        self.joint_names = ["lwr_arm_0_joint",
                            "lwr_arm_1_joint",
                            "lwr_arm_2_joint",
                            "lwr_arm_3_joint",
                            "lwr_arm_4_joint",
                            "lwr_arm_5_joint",
                            "lwr_arm_6_joint"]

        # Subscribes to information about what the current joint values are.
        rospy.Subscriber("/joint_states", sensor_msgs.msg.JointState, 
                         self.joint_states_callback)

        # Subscribe to command for motion planning goal
        rospy.Subscriber("/motion_planning_goal", geometry_msgs.msg.Transform,
                         self.move_arm_cb)

        # Publish trajectory command
        self.pub_trajectory = rospy.Publisher("/joint_trajectory", trajectory_msgs.msg.JointTrajectory, 
                                              queue_size=1)        

        # Initialize variables
        self.joint_state = sensor_msgs.msg.JointState()

        # Wait for moveit IK service
        rospy.wait_for_service("compute_ik")
        self.ik_service = rospy.ServiceProxy('compute_ik',  moveit_msgs.srv.GetPositionIK)
        print "IK service ready"

        # Wait for validity check service
        rospy.wait_for_service("check_state_validity")
        self.state_valid_service = rospy.ServiceProxy('check_state_validity',  
                                                      moveit_msgs.srv.GetStateValidity)
        print "State validity service ready"

        # Initialize MoveIt
        self.robot = moveit_commander.RobotCommander()
        self.scene = moveit_commander.PlanningSceneInterface()
        self.group_name = "lwr_arm"
        self.group = moveit_commander.MoveGroupCommander(self.group_name) 
        print "MoveIt! interface ready"

        # Options
        self.subsample_trajectory = True
        print "Initialization done."

    def get_joint_val(self, joint_state, name):
        if name not in joint_state.name:
            print "ERROR: joint name not found"
            return 0
        i = joint_state.name.index(name)
        return joint_state.position[i]

    def set_joint_val(self, joint_state, q, name):
        if name not in joint_state.name:
            print "ERROR: joint name not found"
        i = joint_state.name.index(name)
        joint_state.position[i] = q

    """ Given a complete joint_state data structure, this function finds the values for 
    our arm's set of joints in a particular order and returns a list q[] containing just 
    those values.
    """
    def q_from_joint_state(self, joint_state):
        q = []
        for i in range(0,self.num_joints):
            q.append(self.get_joint_val(joint_state, self.joint_names[i]))
        return q

    """ Given a list q[] of joint values and an already populated joint_state, this 
    function assumes that the passed in values are for a our arm's set of joints in 
    a particular order and edits the joint_state data structure to set the values 
    to the ones passed in.
    """
    def joint_state_from_q(self, joint_state, q):
        for i in range(0,self.num_joints):
            self.set_joint_val(joint_state, q[i], self.joint_names[i])

    """ This function will perform IK for a given transform T of the end-effector. It 
    returns a list q[] of 7 values, which are the result positions for the 7 joints of 
    the left arm, ordered from proximal to distal. If no IK solution is found, it 
    returns an empy list.
    """
    def IK(self, T_goal):
        req = moveit_msgs.srv.GetPositionIKRequest()
        req.ik_request.group_name = self.group_name
        req.ik_request.robot_state = moveit_msgs.msg.RobotState()
        req.ik_request.robot_state.joint_state = self.joint_state
        req.ik_request.avoid_collisions = True
        req.ik_request.pose_stamped = geometry_msgs.msg.PoseStamped()
        req.ik_request.pose_stamped.header.frame_id = "world_link"
        req.ik_request.pose_stamped.header.stamp = rospy.get_rostime()
        req.ik_request.pose_stamped.pose = convert_to_message(T_goal)
        req.ik_request.timeout = rospy.Duration(3.0)
        res = self.ik_service(req)
        q = []
        if res.error_code.val == res.error_code.SUCCESS:
            q = self.q_from_joint_state(res.solution.joint_state)
        return q

    """ This function checks if a set of joint angles q[] creates a valid state, or 
    one that is free of collisions. The values in q[] are assumed to be values for 
    the joints of the left arm, ordered from proximal to distal. 
    """
    def is_state_valid(self, q):
        req = moveit_msgs.srv.GetStateValidityRequest()
        req.group_name = self.group_name
        current_joint_state = deepcopy(self.joint_state)
        current_joint_state.position = list(current_joint_state.position)
        self.joint_state_from_q(current_joint_state, q)
        req.robot_state = moveit_msgs.msg.RobotState()
        req.robot_state.joint_state = current_joint_state
        res = self.state_valid_service(req)
        return res.valid
        
  # Generate a random sample
    def sample(self, q_min, q_max, n):
        new_config = [random.uniform(q_min[i], q_max[i]) for i in range(n)]
        return numpy.array(new_config)

    # This function generate a new configuration in the direction of random sample in epsilon distance.
    # nn_jointVal - nn stands for nearest neighbour.
    def new_config_generator(self, nn_config, random_sample, epsilon):
        distance = numpy.linalg.norm(nn_config - random_sample)

        if distance < epsilon:
            return random_sample
        else:
            new_config = nn_config + epsilon * ((random_sample - nn_config) / distance)
            return new_config

    # compares the given configuration difference with fixed resolution(q_sample).
    def is_less(self, query):
        for ai, bi in zip(self.q_sample, query):
            if ai > bi:
                pass
            else:
                return False
        return True

    # check collision along the length of specified configurations
    def extend_until(self, nn_config, new_config):
        if self.is_less(numpy.absolute(nn_config - new_config)):
            if not self.is_state_valid(new_config):
                return nn_config, False
        else:
            midpoint = (nn_config + new_config) / 2.0
            node_, goal_reached = self.extend_until(nn_config, midpoint)
            if not goal_reached:
                return node_, goal_reached
            node_, goal_reached = self.extend_until(midpoint, new_config)
            if not goal_reached:
                return node_, goal_reached
        return new_config, True

    def smoothen(self, path):
        points = len(path)
        max_index = points-1
        current_config = [path[0]]
        next_index = 1
        smoothened_path = []
        while current_config:
            left_config = current_config.pop()
            smoothened_path.append(left_config)
            for i in range(max_index, -1, -1):
                right_config = path[i]
                node_, succeed_ = self.extend_until(left_config, right_config)
                if succeed_:
                    next_index = i
                    current_config.append(node_)
                    break
            if next_index == max_index:
                smoothened_path.append(path[max_index])
                break
        return smoothened_path     
        
    def motion_plan(self, q_start, q_goal, q_min, q_max):
        # converting into numpy array
        start = numpy.array(q_start)
        goal = numpy.array(q_goal)
        # variables
        n = len(q_start)
        epsilon = 0.5  # Can be varied - step size towards the random sample
        K = 1000  # maximum number of samples before timeout

        # initialize Node:
        root_node = RRT_Node(start)

        # initialize Tree
        T = RRTSearchTree(root_node)

        for each in range(0, K):
            random_config = self.sample(q_min, q_max, n)
            nearest_node, dist = T.find_nearest(random_config)
            new_config = self.new_config_generator(nearest_node.state, random_config, epsilon)
            collision_free_config, succeed = self.extend_until(nearest_node.state, new_config)
            new_node = RRT_Node(collision_free_config, nearest_node)
            T.add_node(new_node)
            # check for direct connection with goal
            some_thing, succeed = self.extend_until(new_node.state, goal)
            if succeed:
                goal_node = RRT_Node(goal, new_node)
                T.add_node(goal_node)
                break

        path = T.get_back_path(T.nodes[-1])

        # smoothening the path
        Final_path = self.smoothen(path)
        return Final_path
    
    def create_trajectory(self, q_list, v_list, a_list, t):
        joint_trajectory = trajectory_msgs.msg.JointTrajectory()
        for i in range(0, len(q_list)):
            point = trajectory_msgs.msg.JointTrajectoryPoint()
            point.positions = list(q_list[i])
            point.velocities = list(v_list[i])
            point.accelerations = list(a_list[i])
            point.time_from_start = rospy.Duration(t[i])
            joint_trajectory.points.append(point)
        joint_trajectory.joint_names = self.joint_names
        return joint_trajectory

    def create_trajectory(self, q_list):
        joint_trajectory = trajectory_msgs.msg.JointTrajectory()
        for i in range(0, len(q_list)):
            point = trajectory_msgs.msg.JointTrajectoryPoint()
            point.positions = list(q_list[i])
            joint_trajectory.points.append(point)
        joint_trajectory.joint_names = self.joint_names
        return joint_trajectory

    def project_plan(self, q_start, q_goal, q_min, q_max):
        q_list = self.motion_plan(q_start, q_goal, q_min, q_max)
        joint_trajectory = self.create_trajectory(q_list)
        return joint_trajectory

    def move_arm_cb(self, msg):
        T = convert_from_trans_message(msg)
        self.mutex.acquire()
        q_start = self.q_from_joint_state(self.joint_state)
        print "Solving IK"
        q_goal = self.IK(T)
        if len(q_goal)==0:
            print "IK failed, aborting"
            self.mutex.release()
            return
        print "IK solved, planning"
        trajectory = self.project_plan(numpy.array(q_start), q_goal, self.q_min, self.q_max)
        if not trajectory.points:
            print "Motion plan failed, aborting"
        else:
            print "Trajectory received with " + str(len(trajectory.points)) + " points"
            self.execute(trajectory)
        self.mutex.release()
        
    def joint_states_callback(self, joint_state):
        self.mutex.acquire()
        self.joint_state = joint_state
        self.mutex.release()

    def execute(self, joint_trajectory):
        self.pub_trajectory.publish(joint_trajectory)

if __name__ == '__main__':
    moveit_commander.roscpp_initialize(sys.argv)
    rospy.init_node('move_arm', anonymous=True)
    ma = MoveArm()
    rospy.spin()