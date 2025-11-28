"""
Module handles parsing of ASV Spin Mill FIB milling angle reference images.
"""
import logging
from PySide6.QtCore import QObject, Signal
from pathlib import Path


class FIBImageParser(QObject):

    error_signal: Signal = Signal(str)

    def __init__(self, file_path_list: list):
        super().__init__()
        self.file_path_list: list = file_path_list
        self.grand_metadata: dict = {}

    def gather_metadata_from_image(self, file_path_list: list) -> dict:
        single_image_metadata: list = []
        # iterate through the file path list. open the image file and read as bytes.
        try:
            for f in file_path_list:
                with open(f, "rb") as file:
                    # get file name from path
                    file_name = Path(f).name
                    # gather all metadata from the image
                    lines = file.readlines()
                    for line in lines:
                        # convert to string and remove characters such as b, ', and \r\n
                        new_line = str(line[:-2])[2:].replace("'", "")
                        single_image_metadata.append(new_line)
                        # break if the line contains </Metadata>
                        if "</Metadata>" in str(line):
                            break
                    # create dictionary for metadata
                    self.grand_metadata[file_name] = {}
                # gather metadata from the metadata list
                for i, item in enumerate(single_image_metadata):
                    # get stage x, y, z, r, and t values (from SAL/xT)
                    if "<StagePosition>" in item:
                        _stage_x = single_image_metadata[i + 1]. \
                            replace("<X>", "").replace("</X>", "").strip()
                        _stage_y = single_image_metadata[i + 2]. \
                            replace("<Y>", "").replace("</Y>", "").strip()
                        _stage_z = single_image_metadata[i + 3]. \
                            replace("<Z>", "").replace("</Z>", "").strip()
                        _stage_r = single_image_metadata[i + 4]. \
                            replace("<Rotation>", "").replace("</Rotation>", "").strip()
                        _stage_t = single_image_metadata[i + 6]. \
                            replace("<Alpha>", "").replace("</Alpha>", "").strip()
                        self.grand_metadata[file_name]["Stage X"] = float(_stage_x)
                        self.grand_metadata[file_name]["Stage Y"] = float(_stage_y)
                        self.grand_metadata[file_name]["Stage Z"] = float(_stage_z)
                        self.grand_metadata[file_name]["Stage R"] = float(_stage_r)
                        self.grand_metadata[file_name]["Stage T"] = float(_stage_t)
                    # get scan rotation
                    if "<ScanRotation>" in item:
                        _scan_rotation = item.replace("<ScanRotation>", "").replace("</ScanRotation>", "").strip()
                        self.grand_metadata[file_name]["Scan Rotation"] = float(_scan_rotation)
                    # get working distance
                    if "<WorkingDistance>" in item:
                        _working_distance = item.replace("<WorkingDistance>", "").replace("</WorkingDistance>", "").strip()
                        self.grand_metadata[file_name]["Working Distance"] = float(_working_distance)
                # clear the single metadata list to be ready for the next image
                single_image_metadata.clear()
            # sort the grand metadata dictionary
            self.grand_metadata = dict(sorted(self.grand_metadata.items()))
            return self.grand_metadata
        except:
            logging.error(f"exception occurred", exc_info=True)
            self.error_signal.emit("Exception occurred during image parsing")
            return self.grand_metadata
