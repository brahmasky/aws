import datetime, logging, boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from pysnmp.hlapi import *

# from pysnmp import debug
# import pysnmp

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
# debug.setLogger(debug.Debug('io', 'secmod', 'msgproc'))

snmp_secrete_name = '<SNMP_SECRETE_NAME>'
snmp_username = '<SNMP_USER>'
snmp_port = '<SNMP_PORT>'

def get_secret_aws(secret_id):
  '''Returns secrets from secrets manager'''
  try:
      # print('boto3 version == {}'.format(boto3.__version__))
      client = boto3.client('secretsmanager', region_name='ap-southeast-2')
      response = client.get_secret_value(SecretId=secret_id)
      
      return response['SecretString']

  except ClientError as err:
      print('I got a problem')
      return err.response['Error']['Message']

def tanos_instances():
  '''Returns a list of TanOS instances with 'Role' tag'''

  try:
    ec2 = boto3.resource('ec2', region_name='ap-southeast-2')
    filters = [{'Name': 'tag-key','Values': ['Role']}]

    return ec2.instances.filter(Filters=filters)

  except ClientError as err:
    print('Failed to retrieve ec2 instance')
    return err.response['Error']['Message']

def snmp_get(user, password, server, port, oid):
  '''Returns a value from snmp get with the OID, using SNMPv3 protocol '''

  # print('polling {}:{} with user "{}" and pwd "{}" '.format(server, port,user,password))
  iterator = getCmd(
      SnmpEngine(),
      UsmUserData(user, password, password,
              authProtocol=usmHMACSHAAuthProtocol,
              privProtocol=usmAesCfb128Protocol),
      UdpTransportTarget((server, port)),
      ContextData(),
      ObjectType(ObjectIdentity(oid))
  )
  errorIndication, errorStatus, errorIndex, varBinds = next(iterator)
  # print(errorIndication, errorStatus, errorIndex, varBinds)
  print('varBinds length is {}'.format((len(varBinds))))

  if errorIndication:
      print(errorIndication)
  elif errorStatus:
      print('%s at %s' % (errorStatus.prettyPrint(), errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
  else:
      for varBind in varBinds:
          snmp_value = str(varBind).split(' = ')[1]
          print(' = '.join([x.prettyPrint() for x in varBind]))
  return snmp_value

def snmp_walk(user, password, server, port, base_oid):
  '''Returns a dict of snmp walk result from a base OID  '''

  snmp_walk_value={}
  for (errorIndication,errorStatus,errorIndex,varBinds) in nextCmd(
      SnmpEngine(),
      UsmUserData(user, password, password,
              authProtocol=usmHMACSHAAuthProtocol,
              privProtocol=usmAesCfb128Protocol),
      UdpTransportTarget((server, port)),
      ContextData(),
      ObjectType(ObjectIdentity(base_oid)),
      lexicographicMode=False
  ):

    if errorIndication:
        print(errorIndication)
        break
    elif errorStatus:
        print('%s at %s' % (errorStatus.prettyPrint(), errorIndex and varBinds[int(errorIndex) - 1][0] or '?'))
        break
    else:
      # print('lenght of varBinds: {}'.formatlen(varBinds))
      for name, value in varBinds:
        snmp_walk_value[str(name)] = str(value)
        # print(' = '.join([x.prettyPrint() for x in varBind]))
  return snmp_walk_value

def memory_util_metrics(snmp_memory):
  """ Memory utilisation calculation and formatting
  Parameters:
  snmp_memory (dict): SNMP walk result on memory
  Returns: 
  list: two dict for memory size in bytes and memory utilisation in percentage, formatted for CloudWatch metrics
  
  Reference: 
  memory calculation referred to https://support.solarwinds.com/SuccessCenter/s/article/NET-SNMP-memory-calculation?language=en_US
  """

  snmp_memory_total_ram = int(snmp_memory['1.3.6.1.4.1.2021.4.5.0'])
  snmp_memory_total_ram_avail = int(snmp_memory['1.3.6.1.4.1.2021.4.6.0'])
  snmp_memory_total_ram_buffered = int(snmp_memory['1.3.6.1.4.1.2021.4.14.0'])
  snmp_memory_total_ram_cached = int(snmp_memory['1.3.6.1.4.1.2021.4.15.0'])
  
  total_ram_used = snmp_memory_total_ram - snmp_memory_total_ram_avail
  used_memory = total_ram_used - snmp_memory_total_ram_buffered - snmp_memory_total_ram_cached
  memory_utilisation_percent = round((used_memory/snmp_memory_total_ram)*100, 2)

  # list of two memory metrics
  list_memory_metrics=[]

  # dict of totoal memory size
  # [ "SNMP/Memory", "MemoryTotalBytes", "InstanceId", "i-044d0e2df33fb6a08" ]
  dict_memory_total={}
  dict_memory_total['Namespace'] = 'SNMP/Memory'
  dict_memory_total['MetricName'] = 'MemoryTotalKB'
  dict_memory_total['MetricUnit'] = 'Kilobytes'
  dict_memory_total['MetricValue'] = snmp_memory_total_ram
  dict_memory_total['MetricDimension'] = 'InstanceId'
  list_memory_metrics.append(dict_memory_total)

  # dict of memory utilisation
  # [ "SNMP/Memory", "MemoryUtilization", "InstanceId", "i-044d0e2df33fb6a08" ]
  dict_memory_util={}
  dict_memory_util['Namespace'] = 'SNMP/Memory'
  dict_memory_util['MetricName'] = 'MemoryUtilisation'
  dict_memory_util['MetricUnit'] = 'Percent'
  dict_memory_util['MetricValue'] = memory_utilisation_percent
  dict_memory_util['MetricDimension'] = 'InstanceId'
  list_memory_metrics.append(dict_memory_util)

  return list_memory_metrics


def not_tmpfs(vol):
  '''Check if a disk volume is a tmpfs'''

  api_fs_list = ['/sys/fs/cgroup', '/dev/shm', '/dev', '/mnt/menus_tmp']
  if vol.startswith('/') and not vol.startswith('/run') and vol not in api_fs_list:
    return True
  else:
    return False

def disk_util_metrics(snmp_disks):
  """ Disk volume space utilisation calculation and formatting
  Parameters:
  snmp_disks (dict): SNMP walk result on disk volumes
  Returns: 
  list: list of dict for each volume from a tanos instance, formatted for CloudWatch metrics
  
  Reference: 
  disk space calculation formula referred to https://support.solarwinds.com/SuccessCenter/s/article/How-Orion-calculates-volume-metrics-on-a-SNMP-monitored-node?language=en_US
  """

  # hrStorageDescr at 1.3.6.1.2.1.25.2.3.1.3
  # hrStorageAllocationUnits at 1.3.6.1.2.1.25.2.3.1.4
  # hrStorageSize at 1.3.6.1.2.1.25.2.3.1.5
  # hrStorageUsed at 1.3.6.1.2.1.25.2.3.1.6

  disk_name_prefix = '1.3.6.1.2.1.25.2.3.1.3.'
  disk_unit_prefix = '1.3.6.1.2.1.25.2.3.1.4.'
  disk_size_prefix = '1.3.6.1.2.1.25.2.3.1.5.'
  disk_used_prefix = '1.3.6.1.2.1.25.2.3.1.6.'

  disk_name_dict = {}
  disk_unit_dict = {}
  disk_size_dict = {}
  disk_used_dict = {}

  # disk_size_used_dict = {}

  for key,value in snmp_disks.items():
    new_key = key[key.rfind('.')+1:]
    if key.startswith(disk_name_prefix):
      disk_name_dict[new_key] = str(value)
    elif key.startswith(disk_unit_prefix):
      disk_unit_dict[new_key] = int(value)
    elif key.startswith(disk_size_prefix):
      disk_size_dict[new_key] = int(value)
    elif key.startswith(disk_used_prefix):
      disk_used_dict[new_key] = int(value)

  list_volume_metrics=[]
  for key,value in disk_name_dict.items():
    # excluding tmpfs from the result
    if not_tmpfs(value):
      disk_space_total = int(disk_size_dict[key])*int(disk_unit_dict[key])
      disk_space_used = int(disk_used_dict[key])*int(disk_unit_dict[key])
      # disk_utilisation_percent = (hrStorageSize - hrStorageUsed) /100
      disk_space_percent = round((disk_space_used/disk_space_total)*100, 2)
      # disk name as key for the result
      # disk_size_used_dict[value] = [disk_space_total, disk_space_percent]

      # dict for volume size
      dict_volume_total={}
      # [ "SNMP/Volume", "VolumeSize", "VolumeId", "i-044d0e2df33fb6a08-/opt" ]
      dict_volume_total['Namespace'] = 'SNMP/Volume'
      dict_volume_total['MetricName'] = 'VolumeSize'
      dict_volume_total['MetricUnit'] = 'Kilobytes'
      dict_volume_total['MetricValue'] = round(disk_space_total/1024)
      dict_volume_total['MetricDimension'] = 'VolumeId'
      # an extra key to be used to compose the unique volume dimension
      dict_volume_total['VolumeId'] = value
      list_volume_metrics.append(dict_volume_total)

      # dict for volume utilisation
      dict_volume_util={}
      # [ "SNMP/Volume", "VolumeUtilisation", "VolumeId", "i-044d0e2df33fb6a08-/opt" ]
      dict_volume_util['Namespace'] = 'SNMP/Volume'
      dict_volume_util['MetricName'] = 'VolumeUtilisation'
      dict_volume_util['MetricUnit'] = 'Percent'
      dict_volume_util['MetricValue'] = disk_space_percent
      dict_volume_util['MetricDimension'] = 'VolumeId'
      # an extra key to be used to compose the unique volume dimension
      dict_volume_util['VolumeId'] = value
      list_volume_metrics.append(dict_volume_util)

  return list_volume_metrics

def publish_metric(instance_id, metrics):
  """ publish metrics to Cloud Watch
  Parameters:
  instance_id (str): instance id for the tanos instance
  metrics (list): list of pre-formatted dict for memory or disk metrics
  Returns: 
  publish_result: respone from Cloud Watch for the publishing activity
  """

  # initialise Cloud Watch client
  cw_client = boto3.client('cloudwatch', region_name='ap-southeast-2')

  # timestamp to be used for metrics, should capture the time during SNMP walk but leave it for now
  cur_time = datetime.datetime.now()

  publish_result = []
  for metric in metrics:

    metric_name_space = metric['Namespace']

    if metric_name_space == 'SNMP/Memory':
      metric_dimension_value = instance_id
    else:
      metric_dimension_value = instance_id + ':' + metric['VolumeId']

    response = cw_client.put_metric_data(
        Namespace=metric_name_space,
        MetricData=[
          {
            'Timestamp': cur_time,
            'MetricName': metric['MetricName'],
            'Dimensions': [
                {
                    'Name': metric['MetricDimension'],
                    'Value': metric_dimension_value
                },
            ],
            'Value': metric['MetricValue'],
            'Unit': metric['MetricUnit']
          },
        ]
    )

    publish_result.append(response)

  return publish_result

def lambda_handler(event, context):
  """ A lambda function to do SNMP polling and publish metrics to Cloud Watch using pysnmp lib
  Reference: https://fastavares.medium.com/snmp-monitoring-on-aws-lambda-65ffcfd24c6a
  """
  # print('python version == {}'.format(sys.version_info))

  snmp_password = get_secret_aws(snmp_secrete_name)
  tanos = tanos_instances()

  oid_base_mem = '1.3.6.1.4.1.2021.4'
  oid_base_disk = '1.3.6.1.2.1.25.2.3'

  snmp_output = []
  for instance in tanos:
    instance_id = instance.id
    instance_ip = instance.private_ip_address
    instance_name = [tag['Value'] for tag in instance.tags if tag['Key'] == 'Name'][0]

    # snmp walk for memory readings and calculation
    snmp_memory = snmp_walk(snmp_username, snmp_password, instance_ip, snmp_port, oid_base_mem)
    snmp_memory_util = memory_util_metrics(snmp_memory)
  
    # snmp walk for disk readings and calculation
    snmp_disks = snmp_walk(snmp_username, snmp_password, instance_ip, snmp_port, oid_base_disk)
    snmp_disk_util = disk_util_metrics(snmp_disks)

    # publish metrics
    response = publish_metric(instance_id, snmp_memory_util+snmp_disk_util)

    snmp_output.append(dict([
      ('instance_name', instance_name), 
      ('instance_ip', instance_ip), 
      ('instance_id',instance_id ), 
      ('memory', snmp_memory_util),
      ('disk', snmp_disk_util),
    ]))

  return {
      'snmp output': snmp_output,
      'result': response
  }
