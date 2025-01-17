#!/usr/bin/env python

# Copyright (c) 2019 Computer Vision Center (CVC) at the Universitat Autonoma de
# Barcelona (UAB).
#
# This work is licensed under the terms of the MIT license.
# For a copy, see <https://opensource.org/licenses/MIT>.

# Modified by cv4ad

import glob
import os
import sys
import carla # type: ignore <-- what is this
import random
import time
import math
import math
import yaml

# Global configuration
SECONDS_PER_TICK = 5.0 # seconds per tick

#WEATHER STUFF

class Sun(object):
    def __init__(self, azimuth, altitude):
        self.azimuth = azimuth
        self.altitude = altitude
        self._t = 0.0

    def set_azimuth(self, azimuth):
        self.azimuth = azimuth
    
    def set_altitude(self, altitude):
        self.altitude = altitude

    def __str__(self):
        return 'Sun(alt: %.2f, azm: %.2f)' % (self.altitude, self.azimuth)


class Weather(object):
    def __init__(self, weather, configs):
        self.weather = weather
        self._sun = Sun(weather.sun_azimuth_angle, weather.sun_altitude_angle)
        with open(configs, 'r') as file:
            self.states = iter(yaml.safe_load(file)['states'])

    def next(self):
        state = self.states.__next__()
        print(f"setting weather to", state['name'])

        # self._sun.set_azimuth(state.azimuth) see the comment on alititude in the yaml
        self._sun.set_altitude(state['altitude'])

        self.weather.cloudiness = state['cloudiness']
        self.weather.precipitation = state['precipitation']
        self.weather.precipitation_deposits = state['precipitation_deposits']
        self.weather.wind_intensity = state['wind_intensity']
        self.weather.fog_density = state['fog_density']
        self.weather.wetness = state['wetness']
        
        self.weather.sun_azimuth_angle = self._sun.azimuth
        self.weather.sun_altitude_angle = self._sun.altitude

    def __str__(self):
        return '%s %s' % (self._sun, self._storm)
    
class Ego_Vehicle():
    def __init__(self, blueprint, world, spawn_point):
        self.bp = blueprint
        self.spawn_point = spawn_point
        self.cameras = []
        self.world = world

        # Now we need to give an initial transform to the vehicle. We choose a
        # random transform from the list of recommended spawn points of the map.
        transform = spawn_point

        # So let's tell the world to spawn the vehicle.
        self.vehicle = world.spawn_actor(blueprint, transform)
        self.vehicle.set_autopilot(True)
        print('created %s' % self.vehicle.type_id)

    def add_camera(self, blueprint, camera_transform, listen):
        blueprint.set_attribute('sensor_tick', str(SECONDS_PER_TICK))
        camera = self.world.spawn_actor(blueprint, camera_transform, attach_to=self.vehicle)
        camera.listen(listen)
        self.cameras.append(camera)
        print('created %s' % camera.type_id)


def save_image(image, counter, name, file_type, cc = None):
    image_path = f'{name}_{counter.value}.{file_type}'
    if cc:
        image.save_to_disk(image_path, cc)
    else:
        image.save_to_disk(image_path)
    counter.increment()

# ! Temporary function to fill the scene with vehicles and pedestrians. We should paratmetrize and organize this so that we can configure the scene easily
def initialize_agents(world, client, actor_list, traffic_manager, spawn_points):
    # Select some models from the blueprint library
    models = ['dodge', 'audi', 'model3', 'mini', 'mustang', 'lincoln', 'prius', 'nissan', 'crown', 'impala']
    blueprints = []
    for v in world.get_blueprint_library().filter('*vehicle*'):
        if any(model in v.id for model in models):
            blueprints.append(v)

    # Set a max number of vehicles and prepare a list for those we spawn
    max_vehicles = 20
    max_vehicles = min([max_vehicles, len(spawn_points)])
    vehicles = []
    
    for i, spawn_point in enumerate(random.sample(spawn_points, max_vehicles)):
        temp = world.try_spawn_actor(random.choice(blueprints), spawn_point)
        if temp is not None:
            vehicles.append(temp)

    for v in vehicles:
        v.set_autopilot(True) 
        traffic_manager.random_left_lanechange_percentage(v, 0)
        traffic_manager.random_right_lanechange_percentage(v, 0)
        traffic_manager.auto_lane_change(v, False)  
    
    # Spawn walkers
    blueprint_library = world.get_blueprint_library()
    walker_bp = blueprint_library.filter('walker.pedestrian.*')
    walker_controller_bp = blueprint_library.find('controller.ai.walker')

    walkers = []
    controllers = []

    spawn_points = []
    for i in range(100):
        spawn_point = carla.Transform()
        spawn_point.location = world.get_random_location_from_navigation()
        if spawn_point.location is not None:
            spawn_points.append(spawn_point)

    sbatch = []
    for spawn_point in spawn_points:
        walker_bp_choice = random.choice(walker_bp)
        sbatch.append(carla.command.SpawnActor(walker_bp_choice, spawn_point))

    results = client.apply_batch_sync(sbatch, True)

    for result in results:
        if not result.error:
            walkers.append(result.actor_id)

    batch = []
    for walker_id in walkers:
        batch.append(carla.command.SpawnActor(walker_controller_bp, carla.Transform(), walker_id))

    results = client.apply_batch_sync(batch, True)

    for result in results:
        if not result.error:
            controllers.append(result.actor_id)

    walker_actors = [world.get_actor(w) for w in walkers]
    controller_actors = [world.get_actor(c) for c in controllers]

    for controller in controller_actors:
        controller.start()
        controller.go_to_location(world.get_random_location_from_navigation())
        controller.set_max_speed(random.uniform(1.0, 3.0))  # Random speeds

    print(f"Spawned {len(walkers)} walkers.")

    actor_list.extend(walker_actors)
    actor_list.extend(controller_actors)

    return vehicles

def main():
    try:
        sys.path.append(glob.glob('../carla/dist/carla-*%d.%d-%s.egg' % (
            sys.version_info.major,
            sys.version_info.minor,
            'win-amd64' if os.name == 'nt' else 'linux-x86_64'))[0])
    except IndexError:
        pass
    
    actor_list = []
    
    try:
        # Create client and connect to server (the simulator)
        client = carla.Client('localhost', 2000)
        client.set_timeout(10.0)

        # Retrieve the world that is running
        world = client.get_world()

        weather = Weather(world.get_weather(), 'weathers.yaml')
        weather.next()
        world.set_weather(weather.weather)

        # TODO: This is broken. We should figure out how to simulate faster to save some time on our data generation.
        # Change some world setting to make things faster
        # settings = world.get_settings()
        # settings.fixed_delta_seconds = 0.05
        # world.apply_settings(settings)

        traffic_manager = client.get_trafficmanager()

        # The world contains the list of blueprints that we can use for adding new
        # actors into the simulation.
        blueprint_library = world.get_blueprint_library()

        bp = random.choice(blueprint_library.filter('cybertruck')) # ? Why do we filter to only one vehicle type and then randomly select one?
        spawn_points = world.get_map().get_spawn_points()
        spawn_point_1 =  spawn_points[32]

        ego = Ego_Vehicle(bp, world, spawn_point_1)

        # Add our cameras
        #https://github.com/carla-simulator/carla/issues/2176 (bless)
        rgb_cam = blueprint_library.find('sensor.camera.rgb')
        rgb_cam_transform = carla.Transform(carla.Location(x=1.5, z=2.4))

        rgb_seg = blueprint_library.find('sensor.camera.semantic_segmentation')
        rgb_seg_transform = carla.Transform(carla.Location(x=1.5, z=2.4))

        lidar_cam = blueprint_library.find('sensor.lidar.ray_cast')
        lidar_cam_transform = carla.Transform(carla.Location(x=1.5, z=2.4))

        lidar_seg = blueprint_library.find('sensor.lidar.ray_cast_semantic')
        lidar_seg_transform = carla.Transform(carla.Location(x=1.5, z=2.4))

        # TODO: There has got to be a better way to do this.
        class counter():
            def __init__(self, value, name = None):
                self.value = value
                self.name = name

            def increment(self):
                if self.name:
                    print(f'{self.name}: {self.value}')
                self.value += 1
        
        # TODO: do we really need 4 of these?
        rgb_cam_counter = counter(0, 'rgb_cam')
        rgb_seg_counter = counter(0)
        lidar_cam_counter = counter(0)
        lidar_seg_counter = counter(0)

        # Now we register the function that will be called each time the sensor receives an image.
        cc = carla.ColorConverter.Raw
        rgb_cam_listen = lambda image: save_image(image, counter = rgb_cam_counter, 
                        name = '_outRaw/raw', file_type = 'png', cc = cc)
        
        rgb_seg_listen = lambda image: save_image(image, counter = rgb_seg_counter, 
                        name = '_outSeg/seg', file_type = 'png')

        lidar_cam_listen = lambda image: save_image(image, counter = lidar_cam_counter, 
                        name = '_outLIDAR/raw', file_type = 'ply')

        lidar_seg_listen = lambda image: save_image(image, counter = lidar_seg_counter, 
                        name = '_outLIDARseg/seg', file_type = 'ply')

        ego.add_camera(rgb_cam, rgb_cam_transform, rgb_cam_listen)
        ego.add_camera(rgb_seg, rgb_seg_transform, rgb_seg_listen)
        ego.add_camera(lidar_cam, lidar_cam_transform, lidar_cam_listen)
        ego.add_camera(lidar_seg, lidar_seg_transform, lidar_seg_listen)

        # Store so we can delete later. Actors do not get removed automatically
        actor_list.append(ego.vehicle)
        actor_list.extend(ego.cameras)

        # *** Unclear if this needs to stay. We may want randomization in the future to improve the resilience of our model.

        # A blueprint contains the list of attributes that define a vehicle's
        # instance, we can read them and modify some of them. For instance,
        # let's randomize its color.
        # if bp.has_attribute('color'):
        #     color = random.choice(bp.get_attribute('color').recommended_values)
        #     bp.set_attribute('color', color)

        # Route 1
        # Create route 1 from the chosen spawn points
        # route_1_indices = [17, 70, 130, 29, 79, 101, 55, 57, 119, 59, 112, 32]
        # route_1 = []
        # for ind in route_1_indices:
        #     route_1.append(spawn_points[ind].location)

        # traffic_manager.set_path(vehicle, route_1)

        # # But the city now is probably quite empty, let's add a few more
        # # vehicles.
        # transform.location += carla.Location(x=40, y=-3.2)
        # transform.rotation.yaw = -180.0
        # for _ in range(0, 10):
        #     transform.location.x += 8.0

        #     bp = random.choice(blueprint_library.filter('vehicle'))

        #     # This time we are using try_spawn_actor. If the spot is already
        #     # occupied by another object, the function will return None.
        #     npc = world.try_spawn_actor(bp, transform)
        #     if npc is not None:
        #         actor_list.append(npc)
        #         npc.set_autopilot(True)
        #         print('created %s' % npc.type_id)

        # *** 

        vehicles = initialize_agents(world, client, actor_list, traffic_manager, spawn_points)

        # * This can probably go as well, since we now terminate after collecting n images, rather than after a certain amount of time.
        # t_end = time.time() + 2520
        # while time.time() < t_end:

        # * Configure how many images we want per weather scenario from weathers.yaml. Should probably be around 1200. Leave at 2 for testing.
        num_images_per_weather = 2

        last_value = 0
        while True:
            if rgb_cam_counter.value != last_value and rgb_cam_counter.value % num_images_per_weather == 0:
                last_value = rgb_cam_counter.value
                try:
                    weather.next()
                except StopIteration:
                    break
                world.set_weather(weather.weather)

            world.tick()

    finally:
        for camera in ego.cameras: # For some reason, this seems to be necessary evewn though the cameras should be in the actor list, which is destroyed below. Investigate.
            camera.destroy()

        print('destroying actors')
        client.apply_batch([carla.command.DestroyActor(x) for x in actor_list])
        client.apply_batch([carla.command.DestroyActor(x) for x in vehicles]) # Why is this separate from the actor list above?
        print('done.')


if __name__ == '__main__':

    main()
