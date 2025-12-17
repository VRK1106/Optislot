#OptiSlot: Sensor-Less Smart Parking & Optimization System

> **"Sensor-Less Parking Allocation System Using Entrance Dimensional Profiling."**

![Kubernetes](https://img.shields.io/badge/kubernetes-%23326ce5.svg?style=for-the-badge&logo=kubernetes&logoColor=white) ![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white) ![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54) ![OpenCV](https://img.shields.io/badge/opencv-%23white.svg?style=for-the-badge&logo=opencv&logoColor=white)

##Project Overview

**OptiSlot** is a container-native smart parking solution that revolutionizes traditional parking management by moving intelligence from the **Slot** to the **Gate**.

Instead of installing expensive sensors at every single parking spot, OptiSlot uses **Computer Vision** and **Ultrasonic Dimensional Profiling** at the entry gate to detect a vehicle's size. It then uses a **Bin-Packing Algorithm** to dynamically assign the most efficient parking space available.

This "Frugal Engineering" approach reduces hardware infrastructure costs by approximately **95%** while increasing parking surface area efficiency.

---

##Key Features

* **Gate-Centric Architecture:** Eliminates the need for IoT sensors at individual parking slots.
* **Dynamic Space Allocation:** Uses a custom **Bin-Packing Algorithm** to fit vehicles into slots based on their specific dimensions (Small/Medium/Large), acting like "Tetris" for parking lots.
* **Container-Native Deployment:** Fully containerized application running on **Kubernetes** for scalability and self-healing.
* **Robust Data Layer:** Migrated from local file storage to a **Relational SQL Database** to handle high-concurrency transactions and persistent storage.
* **AI-Powered Entry:** Integrates **OpenCV** and **EasyOCR** for Automatic Number Plate Recognition (ANPR) and entry logging.
* **Resilient Networking:** Utilizes **Tunneling Services** to expose local Edge services to the internet without requiring static IPs.

---

##Architecture

The system follows a microservices-inspired architecture:

1.  **The Edge (Gate):** A Python script captures Vehicle Width (Ultrasonic) and License Plate (Camera).
2.  **The Brain (Algorithm):** The system calculates the optimal slot based on current grid occupancy.
3.  **The Cluster:**
    * **Compute:** Docker Containers orchestrated by Kubernetes.
    * **Storage:** SQL Database stores user logs, occupancy grids, and revenue data.
4.  **The Network:** Secure tunnelling bridges the local hardware with the cloud/server resources.

---

##Tech Stack

### Infrastructure & DevOps
* **Containerization:** Docker (Multi-stage builds)
* **Orchestration:** Kubernetes (K8s)
* **Database:** SQL Server / Relational DB
* **Connectivity:** Cloudflare Tunnels / API-based Shorteners

### Backend & AI
* **Language:** Python 3.9+
* **Framework:** Flask (REST API)
* **Computer Vision:** OpenCV, EasyOCR
* **Drivers:** PyODBC (SQL Connectivity)

### Hardware (Prototype)
* **Controller:** Raspberry Pi / Laptop
* **Sensors:** HC-SR04 Ultrasonic Sensor
* **Input:** Standard Webcam

---

##The Logic: Bin-Packing Algorithm

Unlike traditional systems that treat every car as a generic object, OptiSlot categorizes them:

1.  **Scan:** Ultrasonic sensor measures vehicle width at the gate.
2.  **Categorize:** Vehicle is flagged as *Compact, Sedan, or SUV*.
3.  **Allocate:** The algorithm checks the database for the *smallest viable slot* that fits the vehicle.
    * *Result:* A small car is never wasted on a large SUV spot, maximizing revenue per square meter.

---

##Installation & Setup

### Prerequisites
* Docker Desktop installed
* Kubernetes CLI (`kubectl`)
* Python 3.9+

### Local Development
1.  **Clone the repository**
    ```bash
    git clone [https://github.com/yourusername/optislot.git](https://github.com/yourusername/optislot.git)
    cd optislot
    ```

2.  **Set up Environment Variables**
    Create a `.env` file:
    ```env
    SQL_SERVER=your-server-address
    SQL_DB=SmartParkingDB
    SQL_USER=your_admin
    SQL_PWD=your_password
    ```

3.  **Run via Docker Compose**
    ```bash
    docker-compose up --build
    ```

### Deploy to Kubernetes
1.  **Build and Push Image**
    ```bash
    docker build -t your-registry/optislot:v1 .
    docker push your-registry/optislot:v1
    ```

2.  **Apply Kubernetes Manifests**
    ```bash
    kubectl apply -f k8s/deployment.yaml
    kubectl apply -f k8s/service.yaml
    ```

---

##Future Roadmap

* **Analytics Dashboard:** Visualizing revenue trends and peak hours.
* **Edge Processing:** Moving the Computer Vision workload to edge devices for lower latency.
* **Mobile App:** A driver-facing app to reserve spots in advance.

---

##Authors

* **Reshekumar V** - *Lead Backend Developer and Networking*
* **Naveen S** - *Javascript*
* **Sanjai M S** - *AI Model Integration*
* **Pon Prathakshana G** - *HTML & CSS Designer*
* **Rishapthi J** - *Database Management*
* **Razeena Tasneem B** - *Containerizatio Dockers and Kuberenetes*

---

## 📄 License

This project is licensed under the MIT License
