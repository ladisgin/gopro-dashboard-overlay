import math

import geotiler
from PIL import ImageDraw, Image

from .journey import Journey
from .privacy import NoPrivacyZone


class PerceptibleMovementCheck:

    def __init__(self):
        self.last_location = None

    def moved(self, map, location):
        location_of_centre_pixel = map.geocode((map.size[0] / 2, map.size[1] / 2))
        location_of_one_pixel_away = map.geocode(((map.size[0] / 2) + 1, (map.size[1] / 2) + 1))

        x_resolution = abs(location_of_one_pixel_away[0] - location_of_centre_pixel[0])
        y_resolution = abs(location_of_one_pixel_away[1] - location_of_centre_pixel[1])

        if self.last_location is not None:
            x_diff = abs(self.last_location.lon - location.lon)
            y_diff = abs(self.last_location.lat - location.lat)

            if x_diff < x_resolution and y_diff < y_resolution:
                return False

        self.last_location = location
        return True


class JourneyMap:
    def __init__(self, timeseries, at, location, renderer, size=256, corner_radius=None, opacity=0.7,
                 privacy_zone=NoPrivacyZone()):
        self.timeseries = timeseries
        self.privacy_zone = privacy_zone

        self.at = at
        self.location = location
        self.renderer = renderer
        self.corner_radius = corner_radius
        self.opacity = opacity
        self.size = size
        self.map = None
        self.image = None

    def _init_maybe(self):
        if self.map is None:
            journey = Journey()

            self.timeseries.process(journey.accept)

            bbox = journey.bounding_box
            self.map = geotiler.Map(extent=(bbox[0].lon, bbox[0].lat, bbox[1].lon, bbox[1].lat),
                                    size=(self.size, self.size))

            if self.map.zoom > 18:
                self.map.zoom = 18

            plots = [
                self.map.rev_geocode((location.lon, location.lat))
                for location in journey.locations if not self.privacy_zone.encloses(location)
            ]

            image = self.renderer(self.map)

            draw = ImageDraw.Draw(image)
            draw.line(plots, fill=(255, 0, 0), width=4)

            if self.corner_radius:
                image = rounded_corners(image, self.corner_radius, self.opacity)

                draw.rounded_rectangle(
                    (0, 0) + (self.size - 1, self.size - 1),
                    radius=self.corner_radius,
                    outline=(0, 0, 0)
                )
            else:
                draw.line(
                    (0, 0, 0, self.size - 1, self.size - 1, self.size - 1, self.size - 1, 0, 0, 0),
                    fill=(0, 0, 0)
                )

                image.putalpha(int(255 * self.opacity))

            self.image = image

    def draw(self, image, draw):
        self._init_maybe()

        location = self.location()

        frame = self.image.copy()

        draw = ImageDraw.Draw(frame)
        current = self.map.rev_geocode((location.lon, location.lat))
        draw_marker(draw, current, 6)

        image.paste(frame, self.at.tuple())


def draw_marker(draw, position, size, fill=None):
    fill = fill if fill is not None else (0, 0, 255)
    draw.ellipse((position[0] - size, position[1] - size, position[0] + size, position[1] + size),
                 fill=fill,
                 outline=(0, 0, 0))


class MovingMap:
    def __init__(self, at, location, azimuth, renderer,
                 rotate=True, size=256, zoom=17, corner_radius=None, opacity=0.7):
        self.at = at
        self.rotate = rotate
        self.azimuth = azimuth
        self.renderer = renderer
        self.location = location
        self.size = size
        self.zoom = zoom
        self.corner_radius = corner_radius
        self.opacity = opacity
        self.hypotenuse = int(math.sqrt((self.size ** 2) * 2))

        self.half_width_height = (self.hypotenuse / 2)

        self.bounds = (
            self.half_width_height - (self.size / 2),
            self.half_width_height - (self.size / 2),
            self.half_width_height + (self.size / 2),
            self.half_width_height + (self.size / 2)
        )
        self.perceptible = PerceptibleMovementCheck()
        self.cached = None

    def _redraw(self, map):
        map_image = self.renderer(map)

        draw = ImageDraw.Draw(map_image)
        draw_marker(draw, (self.half_width_height, self.half_width_height), 6)
        azimuth = self.azimuth()
        if azimuth and self.rotate:
            azi = azimuth.to("degree").magnitude
            angle = 0 + azi if azi >= 0 else 360 + azi
            map_image = map_image.rotate(angle)

        crop = map_image.crop(self.bounds)

        if self.corner_radius:
            crop = rounded_corners(crop, self.corner_radius, self.opacity)

            ImageDraw.Draw(crop).rounded_rectangle(
                (0, 0) + (self.size - 1, self.size - 1),
                radius=self.corner_radius,
                outline=(0, 0, 0)
            )
        else:
            ImageDraw.Draw(crop).line(
                (
                    0, 0,
                    0, self.size - 1,
                    self.size - 1, self.size - 1,
                    self.size - 1, 0,
                    0, 0
                ),
                fill=(0, 0, 0)
            )

            crop.putalpha(int(255 * self.opacity))

        return crop

    def draw(self, image, draw):
        location = self.location()
        if location.lon is not None and location.lat is not None:

            map = geotiler.Map(center=(location.lon, location.lat), zoom=self.zoom,
                               size=(self.hypotenuse, self.hypotenuse))

            if self.perceptible.moved(map, location):
                self.cached = self._redraw(map)

            image.paste(self.cached, self.at.tuple())


def rounded_corners(frame, radius, opacity):
    mask = Image.new('L', frame.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0) + (frame.size[0] - 1, frame.size[1] - 1), radius=radius,
                                           fill=int(opacity * 255))
    frame.putalpha(mask)
    return frame
