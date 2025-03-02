import glob
import io
from usingCurve import create_curve
from usingCurve import apply_curve
import cv2
import os
import json


files = [file for file in glob.glob("/Data/toledod/cv4ad_carla/imageTestsManipulation*.png")]


points = [(0, 0), (7, 34), (35, 64), (80, 66), (110, 145), (142, 135), (175, 173), (180, 200), (194, 175), (202, 153), (216, 253), (255, 255)]


# Create the curve LUT
curve = create_curve(points)
output_dir = "/Data/toledod/cv4ad_carla/imageTestsManipulation/imagesAfter"
os.makedirs(output_dir, exist_ok=True)
odgt_file_path = "/Data/toledod/cv4ad_carla/test.odgt(night)"

with open(odgt_file_path, 'r') as odgt_file:
    lines = odgt_file.readlines()

for line in lines:
    data = json.loads(line)
    file_name = data["fpath_img"]
    file_nameSeg = data["fpath_segm"]
    print(f"Processing {file_name}")
    file_folder = data["weather"]
    
    with io.open(file_name, 'rb') as image_file:
        image = cv2.imread(file_name)
        # imageSeg = cv2.imread(file_nameSeg)
        enhanced_image = apply_curve(image, curve)

        base_name, ext = os.path.splitext(os.path.basename(file_name))
        new_file_name = f"{base_name}_deweathered{ext}"
        output_folder = os.path.join(output_dir, file_folder)
        os.makedirs(output_folder, exist_ok=True)
        output_file_name = os.path.join(output_folder, new_file_name)
        cv2.imwrite(output_file_name, enhanced_image)
        # cv2.imwrite(output_file_name, imageSeg)