# -*- coding: utf-8 -*-
"""APS360 Project Progress Code

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1r1uQmW-a7pzmRuwgJyeICjiGxWCSV5Gu

heterogeneous vegetation, heterogeneous moisture content, procedurally generated terrain, and
temporally varying wind.

# **DATA LOADING**
Here, we load a tensor of vegetation index data (channel 1) and fire probability data (channel 2).
"""

import ee
import numpy as np
import torch
import torch.nn.functional as F

# Initialize the Earth Engine library.

service_account = 'aps360@ee-vrawal729.iam.gserviceaccount.com'
credentials = ee.ServiceAccountCredentials(service_account, './ee-vrawal729-4fb7eded02e2.json')
ee.Initialize(credentials)

def resize_tensor(input_tensor, target_size=(350, 350)):
    # Ensure the input tensor is in the format of (height, width, channels)
    if len(input_tensor.shape) == 3 and input_tensor.shape[2] == 1:
        input_tensor = input_tensor.permute(2, 0, 1).unsqueeze(0)  # Convert to (1, channels, height, width)
    elif len(input_tensor.shape) == 3 and input_tensor.shape[0] == 1:
        input_tensor = input_tensor.unsqueeze(0)  # Convert to (1, channels, height, width)

    # Use adaptive average pooling to resize the tensor
    resized_tensor = F.adaptive_avg_pool2d(input_tensor, target_size)

    # Squeeze the batch dimension and permute back to the original format
    resized_tensor = resized_tensor.squeeze(0).permute(1, 2, 0)  # Convert to (height, width, channels)

    return resized_tensor

def get_vegetation_tensor(latitude, longitude, start_date, end_date):
    try:
        # Calculate the bounding box for the 350 km by 350 km region
        half_side_length = 175  # Half of 350 km in degrees (approximation)
        lat_min = latitude - half_side_length / 111.32  # 1 degree is approximately 111.32 km
        lat_max = latitude + half_side_length / 111.32
        lon_min = longitude - half_side_length / (111.32 * np.cos(np.deg2rad(latitude)))
        lon_max = longitude + half_side_length / (111.32 * np.cos(np.deg2rad(latitude)))

        # Define the area of interest (AOI)
        aoi = ee.Geometry.Rectangle([lon_min, lat_min, lon_max, lat_max])

        # Load the MODIS vegetation index dataset
        modis = ee.ImageCollection("MODIS/MOD09GA_006_NDVI").filterDate(start_date, end_date).select(['NDVI'])

        # Reduce the collection to a single image by taking the mean
        modis_mean = modis.mean()

        # Set the default projection for the image to 250m
        default_projection = ee.Projection('EPSG:4326').atScale(250)
        modis_mean = modis_mean.setDefaultProjection(default_projection)

        # Clip the image to the AOI
        modis_clipped = modis_mean.clip(aoi)

        # Reproject the image to 1km resolution using average pooling
        modis_reprojected = modis_clipped.reduceResolution(
            reducer=ee.Reducer.mean(),
            bestEffort=True,
            maxPixels=1024
        ).reproject(
            crs='EPSG:4326',
            scale=1000
        )

        # Sample the image to get the values in a 350x350 grid
        sampled = modis_reprojected.sampleRectangle(
            region=aoi,
            defaultValue=0
        )

        # Get the NDVI values as a numpy array
        ndvi_array = np.array(sampled.get('NDVI').getInfo())

        # Ensure the array is the correct size
        if ndvi_array.shape != (350, 350):
            ndvi_array = np.resize(ndvi_array, (350, 350))

        # Add a new axis to make it (350, 350, 1)
        vegetation_tensor = ndvi_array[:, :, np.newaxis]

        # Convert the numpy array to a PyTorch tensor
        vegetation_tensor_pt = torch.tensor(vegetation_tensor, dtype=torch.float32)

        return vegetation_tensor_pt

    except ee.EEException as e:
        print("An error occurred while processing the image:", e)
        return None

# Example usage
'''
vegetation_tensor = get_vegetation_tensor(latitude, longitude)
print(vegetation_tensor)
print(vegetation_tensor.shape)

resized_vegetation_tensor = resize_tensor(vegetation_tensor)
print(resized_vegetation_tensor)
print(resized_vegetation_tensor.shape)
'''

def get_fire_probability_tensor(latitude, longitude, start_date, end_date):
    try:
        # Calculate the bounding box for the 350 km by 350 km region
        half_side_length_km = 175  # Half of 350 km
        scale = 1000  # 1 km per pixel

        # Define the area of interest (AOI)
        aoi = ee.Geometry.Point(longitude, latitude).buffer(half_side_length_km * 1000).bounds()

        # Load the MODIS fire probability dataset
        modis = ee.ImageCollection('MODIS/061/MOD14A1').filterDate(start_date, end_date).select(['FireMask'])

        # Create a function to assign values to FireMask
        def assign_fire_confidence(image):
            fire_mask = image.select('FireMask')
            low_confidence = fire_mask.eq(4).multiply(0.5)
            nominal_confidence = fire_mask.eq(5).multiply(1)
            high_confidence = fire_mask.eq(6).multiply(1)
            fire_confidence = low_confidence.add(nominal_confidence).add(high_confidence)
            return image.addBands(fire_confidence.rename('FireConfidence'))

        # Apply the function to the image collection
        modis_with_confidence = modis.map(assign_fire_confidence)

        # Reduce the collection to a single image by taking the max of 'FireConfidence'
        fire_confidence_image = modis_with_confidence.select('FireConfidence').max()

        # Clip the image to the AOI
        fire_confidence_clipped = fire_confidence_image.clip(aoi)

        # Reproject to ensure the sampling is done correctly
        fire_confidence_reprojected = fire_confidence_clipped.reproject(crs='EPSG:4326', scale=scale)

        # Sample the image to get the values in a 350x350 grid
        fire_prob_array = fire_confidence_reprojected.sampleRectangle(
            region=aoi,
            defaultValue=0
        ).get('FireConfidence').getInfo()

        # Convert the result to a numpy array and ensure it's the correct shape
        fire_prob_array = np.array(fire_prob_array)

        if fire_prob_array.shape != (350, 350):
            fire_prob_array = np.resize(fire_prob_array, (350, 350))

        # Add a new axis to make it (350, 350, 1)
        fire_prob_tensor = fire_prob_array[:, :, np.newaxis]

        # Convert the numpy array to a PyTorch tensor
        fire_prob_tensor_pt = torch.tensor(fire_prob_tensor, dtype=torch.float32)

        return fire_prob_tensor_pt

    except ee.EEException as e:
        print("An error occurred while processing the image:", e)
        return None

# Example usage
'''
fire_prob_tensor = get_fire_probability_tensor(latitude, longitude)
print(fire_prob_tensor)
if fire_prob_tensor is not None:
    print(fire_prob_tensor.shape)  # Should print torch.Size([350, 350, 1])
else:
    print("Failed to retrieve fire probability tensor.")
'''

def concat_tensors(tensor1, tensor2):
    concatenated_tensor = torch.cat((tensor2, tensor1), dim=2)
    return concatenated_tensor

latitude = 43.661900  # Example latitude
longitude = -79.396200  # Example longitude

def get_cnn_tensor(latitude, longitude, start_date, end_date):
    vegetation_tensor = get_vegetation_tensor(latitude=latitude, longitude=longitude, start_date=start_date, end_date=end_date)
    resized_vegetation_tensor = resize_tensor(vegetation_tensor)
    fire_prob_tensor = get_fire_probability_tensor(latitude, longitude, start_date, end_date)
    output_tensor = concat_tensors(fire_prob_tensor, resized_vegetation_tensor)
    return output_tensor

output = get_cnn_tensor(latitude, longitude, '2023-01-01', '2023-12-31')
print(output)
print(output.shape)

"""# **DATA PROCESSING**
Based on a list of longitude and latitude coordinate pairs, we generate a DataLoader iterable of each of our training examples and corresponding labels.
"""

# Commented out IPython magic to ensure Python compatibility.
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import torch.utils.data
# from torch.utils.data import TensorDataset

# Plots and Graphs:
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.express as px
!pip install scikit-plot
import scikitplot as skplt
# %matplotlib inline

import geopandas as gpd
import folium

import requests
from IPython.display import Image, display

import random
import urllib.request

from torch.utils.data import DataLoader, random_split, TensorDataset

import warnings
warnings.filterwarnings('ignore')

from google.colab import files
import io
import os

# Shows all columns
pd.set_option('display.max_columns', None)

df = pd.read_csv('/content/fp-historical-wildfire-data-2006-2023.csv')
df_test = df[['fire_start_date', 'fire_location_latitude', 'fire_location_longitude']]

def remove_second_word(df, column_name):
    if column_name in df.columns:
        # Convert the column to strings first
        df[column_name] = df[column_name].astype(str)
        # Apply the lambda function to remove the second word
        df[column_name] = df[column_name].apply(lambda x: x.split()[0] if ' ' in x else x)
    else:
        raise ValueError(f"Column '{column_name}' not found in the DataFrame")
    return df

df_test = remove_second_word(df_test, 'fire_start_date')
# df_test

date_list = df_test['fire_start_date'].tolist()
lat_list = df_test['fire_location_latitude'].tolist()
long_list = df_test['fire_location_longitude'].tolist()

print(lat_list)
print(date_list)

def get_next_day(date_string):
    date_format = "%Y-%m-%d"
    date_obj = datetime.strptime(date_string, date_format)
    next_day_obj = date_obj + timedelta(days=1)
    return next_day_obj.strftime(date_format)

# print(type(get_next_day('2006-01-01')))
print(date_list[0])
print(get_next_day(date_list[0]))

# print(str(date_list[0]))

# test0 = get_cnn_tensor(lat_list[0], long_list[0], '2006-01-02', '2006-01-03')
# test = get_cnn_tensor(lat_list[0], long_list[0], date_list[0], get_next_day(date_list[0]))

tensors = torch.stack([get_cnn_tensor(lat_list[i], long_list[i], date_list[i], get_next_day(date_list[i])) for i in range(100)])
labels = torch.stack([get_cnn_tensor(lat_list[i], long_list[i], get_next_day(date_list[i]), get_next_day(get_next_day(date_list[i])))[:, :, 1] for i in range(100)])

dataset = torch.utils.data.TensorDataset(tensors, labels)

dataset_size = len(dataset)
train_size = int(0.7 * dataset_size)
valid_size = int(0.2 * dataset_size)
test_size = int(0.1 * dataset_size)

train_dataset, valid_dataset, test_dataset = random_split(dataset, [train_size, valid_size, test_size])

batch_size = 10

train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
valid_loader = DataLoader(valid_dataset, batch_size=batch_size, shuffle=False)
test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False)

"""# **MODEL TRAINING AND TESITNG**

## Helper functions for training, validation, testing, and plotting
"""

## importing NN stuff


# importing pytorch modules
import torch  # pytorch
import torch.nn as nn  # contains NN classes
import torch.nn.functional as F  # contains activation functions
import torch.optim as optim  # contains optimizers

from torchvision import datasets, transforms  # contains ImageLoader
from torch.utils.data import DataLoader  # contains DataLoader
from torch.utils.data.sampler import SubsetRandomSampler

# importing image and matplotlib modules
import matplotlib.pyplot as plt  # plots stuff
import PIL
import urllib

# importing numpy to make life easier
import numpy as np

# importing time module
import time

torch.manual_seed(1)  # setting the random seed to 1 for reproducibility when running code

use_cuda = True

def get_model_name(name, batch_size, learning_rate, epoch):
    """ Generate a name for the model consisting of all the hyperparameter values

    Args:
        config: Configuration object containing the hyperparameters
    Returns:
        path: A string with the hyperparameter name and value concatenated
    """
    path = "model_{0}_bs{1}_lr{2}_epoch{3}".format(name,
                                                   batch_size,
                                                   learning_rate,
                                                   epoch)
    return path

def get_accuracy(model, data_loader):

    correct = 0
    total = 0
    for images, labels in data_loader:

        # Enable GPU Usage
        if use_cuda and torch.cuda.is_available():
          images = images.cuda()
          labels = labels.cuda()

        output = model(images)
        #select index with maximum prediction score
        pred = output.max(1, keepdim=True)[1]
        correct += pred.eq(labels.view_as(pred)).sum().item()
        total += images.shape[0]
    return correct / total

def train_net(Net, train_dataset, val_dataset, bs=64, learning_rate=0.01, num_epochs=30):
    torch.manual_seed(1000)

    # Obtain the PyTorch data loader objects to load batches of the datasets
    train_batch_loader = torch.utils.data.DataLoader(train_dataset, batch_size=bs, shuffle=True)
    val_batch_loader = torch.utils.data.DataLoader(val_dataset, batch_size=bs, shuffle=True)

    # Define the Loss function and optimizer
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.SGD(Net.parameters(), lr=learning_rate, momentum=0.9)

    train_acc = np.zeros(num_epochs)
    val_acc = np.zeros(num_epochs)
    iters = np.zeros(num_epochs)
    losses = np.zeros(num_epochs)

    if use_cuda and torch.cuda.is_available():
        Net = Net.cuda()
    # training
    start_time=time.time()
    n = 0
    for epoch in range(num_epochs):

        for images, labels in iter(train_batch_loader):

            #To Enable GPU Usage
            if use_cuda and torch.cuda.is_available():
              images = images.cuda()
              labels = labels.cuda()

            out = Net(images)             # forward pass
            loss = criterion(out, labels) # compute the total loss
            loss.backward()               # backward pass (compute parameter updates)
            optimizer.step()              # make the updates for each parameter
            optimizer.zero_grad()         # a clean up step for PyTorch

        n+=1
        # save the current training information
        iters = np.append(iters, n)
        losses = np.append(losses, float(loss)/bs)
        # track accuracy
        train_acc[epoch] = get_accuracy(Net, train_loader)
        val_acc[epoch] = get_accuracy(Net, val_loader)
        # Save the current model (checkpoint) to a file
        model_path = get_model_name(Net.name, bs, learning_rate, epoch+1)
        torch.save(Net.state_dict(), model_path)
        # CHECKPOINT
        print("Epoch %d Finished. " % epoch ,"Time per Epoch: % 6.2f s "% ((time.time()-start_time) / (epoch +1)))
        print('Finished Training')
        print(("Epoch {}: Train acc: {} |"+"Validation acc: {}").format(epoch, train_acc[epoch], val_acc[epoch]))

    end_time= time.time()
    # plotting
    plt.title("Training Curve")
    plt.plot(iters, losses, label="Train")
    plt.xlabel("Iterations")
    plt.ylabel("Loss")
    plt.show()

    plt.title("Training Curve")
    plt.plot(iters, train_acc, label="Training")
    plt.plot(iters, val_acc, label="Validation")
    plt.xlabel("Iterations")
    plt.ylabel("Validation Accuracy")
    plt.legend(loc='best')
    plt.show()

    train_acc.append(get_accuracy(Net, train_dataset))
    print("Final Training Accuracy: {}".format(train_acc[-1]))
    print("Final Validation Accuracy: {}".format(val_acc[-1]))
    print ("Total time:  % 6.2f s  Time per Epoch: % 6.2f s " % ( (end_time-start_time), ((end_time-start_time) / num_epochs) ))

"""## Baseline model training and plotting"""

# define a 3-layer artificial neural network as our baseline model
class Baseline(nn.Module):
    def __init__(self):
        super(Baseline, self).__init__()
        self.layer1 = nn.Linear(4 * 350 * 350, 100)
        self.layer2 = nn.Linear(100, 30)
        self.layer3 = nn.Linear(30, 350 * 350)
        self.name = 'Baseline'
    def forward(self, img):
        flattened = img.view(-1, 4 * 350 * 350)
        activation1 = self.layer1(flattened)
        activation1 = F.relu(activation1)
        activation2 = self.layer2(activation1)
        activation2 = F.relu(activation2)
        activation3 = self.layer3(activation2)
        return activation3.squeeze(1)

'''
# instantiating baseline model class object
baseline = Baseline()

train_loader, val_loader, test_loader, classes = get_data_loader(
    target_classes=["cat", "dog"],
    batch_size=128)  # setting 128 images per batch

train_net(pigeon, batch_size=512, learning_rate=0.001, num_epochs=100)

print('Test error:', evaluate(pigeon, test_loader, nn.BCEWithLogitsLoss())[0])
print('Validation error:', evaluate(pigeon, val_loader, nn.BCEWithLogitsLoss())[0])

# plotting the Pigeon training curve
pigeon_model_path = get_model_name('ANN', batch_size=512, learning_rate=0.001, epoch=99)
plot_training_curve(pigeon_model_path)
'''

"""## Preliminary model training and testing"""

class CNNLSTM(nn.Module):
  def __init__(self):
        super(CNNLSTM, self).__init__()
        self.conv1 = nn.Conv2D(3, 30, 10, stride = 2, padding = 2)
        self.conv2 = nn.Conv2D(6, 60, 5, stride = 1, padding = 1)
        # define the transposed convolution layer
        self.conv3UP = nn.ConvTranspose2d(60, 30, 3, stride = 3)
        # define the transposed convolution layer
        self.conv4UP = nn.ConvTranspose2d(30, 1, 4, stride = 2, padding = 66)
        # Averag epooling layer
        self.pool = nn.AvgPool2D(2,2)

  def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        # apply the transposed convolution layer
        x = F.relu(self.conv3UP(x))
        # apply the upsampling function
        x = torch.nn.functional.interpolate(x, scale_factor=2, mode='bilinear')
        # apply the transposed convolution layer
        x = self.conv4UP(x)
        return x



class CNN_FC(nn.Module):
  def __init__(self):
        super(CNNLSTM, self).__init__()
        self.conv1 = nn.Conv2D(3, 30, 10, stride = 2, padding = 2)
        self.conv2 = nn.Conv2D(6, 60, 5, stride = 1, padding = 1)
        self.FC1 = nn.Linear(60*40*40, 100)
        self.FC2 = nn.Linear(100, 1)

        # Average epooling layer
        self.pool = nn.AvgPool2D(2,2)

  def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = F.relu(self.FC1(x))
        x = self.FC2(x)
        return x

"""# **Other Stuff**"""

from google.colab import drive
drive.mount('/content/gdrive')

# unzip file from my drive into my datasets directory in roots on
!unzip '/content/gdrive/MyDrive/APS360/APS360 - Project - Summer 2024/Coding Files/' -d '/root'

https://developers.google.com/earth-engine/datasets/catalog/MODIS_061_MOD13A1

import ee
import requests
import geopandas as gpd
import os

# Initialize the Earth Engine module.
ee.Initialize()

ee.ImageCollection(“NOAA/GOES/16/FDCF”)
ee.ImageCollection(“NOAA/GOES/17/FDCF”)
# Fire
ee.ImageCollection(“MODIS/006/MOD14A1”)


def get_vegetation_data(region, start_date, end_date):
    ndvi_collection = ee.ImageCollection('MODIS/006/MOD13A1')
                      .filterDate(start_date, end_date)
                      .filterBounds(region)
                      .select('NDVI')
                      .mean()
    ndvi_image = ndvi_collection.clip(region)
    url = ndvi_image.getThumbURL({'region': region, 'dimensions': 512, 'format': 'png'})
    return url

import requests
import geopandas as gpd

# Read the shapefile
gdf = gpd.read_file("/root/NFDB_poly_20210707.shp")

# Print the first few rows of the GeoDataFrame
print(gdf.head())

'''def get_fire_perimeter_data():
    url = 'https://cwfis.cfs.nrcan.gc.ca/downloads/nfdb/fire_poly/current_version/NFDB_poly.zip'
    r = requests.get(url)
    with open(UnicodeTranslateError, 'wb') as f:
        f.write(r.content)
    gdf = gpd.read_file('zip://firePerimeters.zip')
    return gdf'''

import ee
import numpy as np
import tensorflow as tf

# Initialize the Earth Engine library.
ee.Initialize()

# Define the area of interest (AOI) and the time range
aoi = ee.Geometry.Rectangle([longitude_min, latitude_min, longitude_max, latitude_max])
start_date = '2023-01-01'
end_date = '2023-12-31'

# Load the MODIS vegetation index dataset
modis = ee.ImageCollection('MODIS/061/MOD13Q1').filterDate(start_date, end_date).select(['NDVI', 'EVI'])

# Reduce the collection to a single image by taking the mean
modis_mean = modis.mean()

# Clip the image to the AOI
modis_clipped = modis_mean.clip(aoi)

# Reproject the image to 1km resolution using average pooling
modis_reprojected = modis_clipped.reduceResolution(
    reducer=ee.Reducer.mean(),
    bestEffort=True,
    maxPixels=1024
).reproject(
    crs='EPSG:4326',
    scale=1000
)

# Sample the image to get the values in a 350x350 grid
sampled = modis_reprojected.sampleRectangle(
    region=aoi,
    defaultValue=0
)

# Get the NDVI and EVI values as numpy arrays
ndvi_array = np.array(sampled.get('NDVI').getInfo())
evi_array = np.array(sampled.get('EVI').getInfo())

# Stack the arrays to create a 350x350x2 tensor
vegetation_tensor = np.stack([ndvi_array, evi_array], axis=-1)

# Convert the numpy array to a TensorFlow tensor
vegetation_tensor_tf = tf.convert_to_tensor(vegetation_tensor, dtype=tf.float32)

# Output the tensor
print(vegetation_tensor_tf)