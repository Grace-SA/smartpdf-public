"""Rectify a small, measured text-line tilt without rotating the document."""
import math
import numpy as np
from PIL import Image


def rectified_line(image, polygon):
    box=np.asarray(polygon,dtype=float)
    delta=box[1]-box[0];width=float(np.linalg.norm(delta))
    if width<2:return None
    u=delta/width;v=np.array([-u[1],u[0]])
    angle=math.degrees(math.atan2(u[1],u[0]))
    height=float(np.dot(box[3]-box[0],v))
    if not .3<=abs(angle)<=8 or height<2:return None
    # Reject perspective, reversed winding and nonrectangular quadrilaterals.
    if max(np.linalg.norm(box[2]-(box[1]+v*height)),np.linalg.norm(box[3]-(box[0]+v*height)))>3:
        return None
    padding=3;origin=box[0]-padding*(u+v)
    size=(math.ceil(width)+2*padding,math.ceil(height)+2*padding)
    corners=[origin,origin+u*size[0],origin+u*size[0]+v*size[1],origin+v*size[1]]
    if any(not (0<=p[0]<image.width and 0<=p[1]<image.height) for p in corners):return None
    crop=image.transform(size,Image.Transform.AFFINE,
        (u[0],v[0],origin[0],u[1],v[1],origin[1]),Image.Resampling.BICUBIC)
    return crop,{'origin':origin,'u':u,'v':v,'angle':angle},[[padding,padding],[padding+width,padding],[padding+width,padding+height],[padding,padding+height]]


def mapped_point(mapping,x,y):
    return mapping['origin']+mapping['u']*x+mapping['v']*y
