import os
import re
import sys
import glob
import boto3
import subprocess


# 指定 main.tf 內容
# function: 能否 terraform init
def check_and_init_terraform():
    main_tf_path = "./main.tf"

    if os.path.exists(main_tf_path):
        subprocess.run(["terraform", "init"], check=True)
    else:
        main_tf_content = """
terraform {
  required_version = "~> 1.9"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.63"
    }
  }
}
"""
        with open(main_tf_path, "w") as file:
            file.write(main_tf_content)

        subprocess.run(["terraform", "init"], check=True)


# 指定 region name
# function: return 該 region cloudwatch name list
def list_alarms(region_name: str):
    alarms_list = []

    cloudwatch_client = boto3.client("cloudwatch", region_name=region_name)

    paginator = cloudwatch_client.get_paginator("describe_alarms")

    for page in paginator.paginate():
        for alarm in page["MetricAlarms"]:
            alarms_list.append(alarm["AlarmName"])

    if len(alarms_list) == 0:
        print(f"No alarms in {region_name}.")
        sys.exit()

    return alarms_list


# function: return terraform import block
def generate_import_blocks(alarms_list: list):
    import_blocks = []

    for alarm in alarms_list:
        import_block = f"""
resource "aws_cloudwatch_metric_alarm" "{alarm}" {{
}}

import {{
  to = aws_cloudwatch_metric_alarm.{alarm}
  id = "{alarm}"
}}
"""
        import_blocks.append(import_block.strip())

    return import_blocks


# 指定 terraform 檔案名稱
# function: 將 import block 制作成 import.tf
def generate_tf_file(import_blocks, region_name: str):
    import_blocks = "\n\n".join(import_blocks)
    terraform_file_name = f"import_alarms_in_{region_name}.tf"

    with open(terraform_file_name, "w") as f:
        f.write(import_blocks)


# function: run terraform import
def terraform_import(alarms_list: list, region_name: str):
    if not alarms_list:
        print(
            f"alarms_list is empty, please check if there is any alarms in {region_name}."
        )
        return

    commands = [
        f"terraform import aws_cloudwatch_metric_alarm.{alarm} {alarm}"
        for alarm in alarms_list
    ]
    full_command = " && ".join(commands)

    process = subprocess.run(full_command, shell=True, capture_output=True, text=True)


# function: 製作成可以 terraform plan 的 .tf
def generate_tf_from_show(region_name: str):
    show_command = f"terraform show -no-color > cloudwatch_alarm_in_{region_name}.tf"

    subprocess.run(show_command, shell=True)


# function: 移除 import.tf
def remove_import_files():
    current_directory = os.getcwd()

    for filename in os.listdir(current_directory):
        if filename.startswith("import"):
            file_path = os.path.join(current_directory, filename)
            try:
                os.remove(file_path)
            except FileNotFoundError:
                print("not found any import related tf file !")


# function: 刪除檔案中的 arn & id
def remove_arn_and_id():
    file_path = glob.glob("./cloudwatch*")[0]

    with open(file_path, "r") as file:
        content = file.readlines()

    # 過濾掉包含 arn 和 id 的行
    updated_content = []
    for line in content:
        if not re.search(r"^\s*arn\s*=|^\s*id\s*=", line):
            updated_content.append(line)

    # 將更新後的內容寫回檔案
    with open(file_path, "w") as file:
        file.writelines(updated_content)


# function: run terraform import
def terraform_plan():
    last_command = "terraform plan"
    subprocess.run(last_command, shell=True)


# 執行區
if __name__ == "__main__":
    # 指定 region
    region_name: str = "us-east-1"

    # 確認能否 terraform init
    print("initializing terraform")
    check_and_init_terraform()

    # 製作 import.tf
    print("creating terraform import file")
    alarms_list = list_alarms(region_name)
    import_file = generate_import_blocks(alarms_list)
    generate_tf_file(import_file, region_name)

    # 製作 resource terraform
    print("--- --- ---")
    print("creating aws resource tf file")
    terraform_import(alarms_list, region_name)
    generate_tf_from_show(region_name)

    # 移除 import.tf
    print("--- --- ---")
    print("removing import.tf file")
    remove_import_files()

    # 修改 terraform 使後續可以直接 plan
    print("--- --- ---")
    print("editing cloudwatch tf file, removing id and arn")
    remove_arn_and_id()

    # 測試 terraform plan 是否為 no changes
    print("--- --- ---")
    print("terraform planning")
    terraform_plan()
