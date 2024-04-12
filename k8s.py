from kubernetes import client, config
import time
from uuid import uuid4

def create_deployment_object(requestor, nats_host, etcd_endpoints, deployment_name):
    # Configureate Pod template container
    image_pull_secret = [client.V1LocalObjectReference(name="regcred")]
    container = client.V1Container(
        name=deployment_name,    
        image="harbor.0x01.host/dgg/voteworker",
        env=[client.V1EnvVar(name="ID", value=requestor),
             client.V1EnvVar(name="NATS_HOST", value=nats_host),
             client.V1EnvVar(name="ETCD_ENDPOINTS", value=etcd_endpoints),
             client.V1EnvVar(name="GIN_MODE", value="release")],
        ports=[client.V1ContainerPort(container_port=80)],
        resources=client.V1ResourceRequirements(
            limits={"memory": "10Mi"},
        ),
    )

    # Create and configure a spec section
    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={
                "app": deployment_name,
                "uuid": deployment_name,
                "id": requestor,
                "app": "hackwrld-client",
                "creationDate": str(int(time.time()))
            },
        ),
        spec=client.V1PodSpec(containers=[container], image_pull_secrets=image_pull_secret),
    )

    # Create the specification of deployment
    spec = client.V1DeploymentSpec(
        replicas=1, template=template, selector={
            "matchLabels":
            {"app": deployment_name}})

    # Instantiate the deployment object
    deployment = client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=client.V1ObjectMeta(name=deployment_name, labels={
            "id": requestor,
            "app": deployment_name,
            "hackwrld-client": "true",
            "name": f"{requestor}-commandcenter",
            "uuid": deployment_name
        }),
        spec=spec,
    )
    return deployment


def get_cc_ip(userId, namespace) -> list:
    config.load_config()
    v1 = client.CoreV1Api()
    mypods = v1.list_namespaced_pod(
        namespace=namespace,
        label_selector=f"id={userId}", 
        watch=False
    )
    ccs = []
    for pod in mypods.items:
        ccs.append({
            "ip": pod.status.pod_ip
        })
    return ccs