"""
Iteration 16 - Test: Mock email notifications, E2E hired->onboarding, template editing
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

def get_token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]

@pytest.fixture(scope="module")
def headers():
    return {"Authorization": f"Bearer {get_token()}", "Content-Type": "application/json"}

def test_health(headers):
    r = requests.get(f"{BASE_URL}/api/dewi/recruitment/candidates", headers=headers)
    assert r.status_code == 200
    print("PASS: candidates endpoint OK")

def test_email_log_on_stage_change(headers):
    """PUT stage -> Interview HR must create email_logs entry"""
    uid = uuid.uuid4().hex[:6]
    create_r = requests.post(f"{BASE_URL}/api/dewi/recruitment/candidates",
                              json={"name": f"TEST_Email_{uid}", "email": f"testemail_{uid}@example.com",
                                    "phone": "081234", "position": "Dev", "stage": "Screening CV",
                                    "source": "Manual", "job_title": "Developer"}, headers=headers)
    assert create_r.status_code in [200, 201], f"Create failed: {create_r.text}"
    cand_id = create_r.json()["candidate"]["candidate_id"]
    print(f"Created candidate: {cand_id}")

    put_r = requests.put(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}",
                          json={"stage": "Interview HR"}, headers=headers)
    assert put_r.status_code == 200, f"Stage change failed: {put_r.text}"
    
    cand = put_r.json().get("candidate", put_r.json())
    logs = cand.get("email_logs", [])
    assert len(logs) >= 1, f"Expected email_logs, got: {logs}"
    log = logs[-1]
    assert log["stage"] == "Interview HR"
    assert log["status"] == "mock_sent"
    assert "Interview HR" in log["subject"]
    print(f"PASS: email_log created - stage={log['stage']}, status={log['status']}")

def test_no_email_no_log(headers):
    """Candidate without email - no email_log on stage change"""
    uid = uuid.uuid4().hex[:6]
    create_r = requests.post(f"{BASE_URL}/api/dewi/recruitment/candidates",
                              json={"name": f"TEST_NoEmail_{uid}", "phone": "081234",
                                    "position": "Dev", "stage": "Screening CV",
                                    "source": "Manual", "job_title": "Developer"}, headers=headers)
    assert create_r.status_code in [200, 201]
    cand_id = create_r.json()["candidate"]["candidate_id"]

    put_r = requests.put(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}",
                          json={"stage": "Interview HR"}, headers=headers)
    assert put_r.status_code == 200
    cand = put_r.json().get("candidate", put_r.json())
    logs = cand.get("email_logs", [])
    assert len(logs) == 0, f"Should have no logs without email, got: {logs}"
    print("PASS: no email_log for candidate without email")

def test_multiple_stage_emails_accumulate(headers):
    """Multiple stage changes accumulate email_logs"""
    uid = uuid.uuid4().hex[:6]
    create_r = requests.post(f"{BASE_URL}/api/dewi/recruitment/candidates",
                              json={"name": f"TEST_Multi_{uid}", "email": f"multi_{uid}@example.com",
                                    "phone": "081234", "position": "Dev", "stage": "Screening CV",
                                    "source": "Manual", "job_title": "Developer"}, headers=headers)
    assert create_r.status_code in [200, 201]
    cand_id = create_r.json()["candidate"]["candidate_id"]

    for stage in ["Interview HR", "Interview User", "Offering"]:
        r = requests.put(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}",
                         json={"stage": stage}, headers=headers)
        assert r.status_code == 200, f"Stage {stage} failed"

    get_r = requests.get(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}", headers=headers)
    assert get_r.status_code == 200
    cand = get_r.json().get("candidate", get_r.json())
    logs = cand.get("email_logs", [])
    assert len(logs) >= 3, f"Expected 3 logs, got {len(logs)}"
    stages = [log["stage"] for log in logs]
    assert "Interview HR" in stages and "Offering" in stages
    print(f"PASS: {len(logs)} email logs accumulated: {stages}")

def test_e2e_hired_creates_onboarding(headers):
    """E2E: Offering -> Hired -> onboarding_checklist_id set + Hired email log"""
    uid = uuid.uuid4().hex[:6]
    # Must include job_id for auto-onboarding to trigger (line 259 in dewi_recruitment.py)
    jobs_r = requests.get(f"{BASE_URL}/api/dewi/recruitment/jobs", headers=headers)
    jobs = jobs_r.json().get("jobs", []) if jobs_r.status_code == 200 else []
    job_id = jobs[0]["job_id"] if jobs else ""
    job_title = jobs[0]["title"] if jobs else "Developer"
    
    create_r = requests.post(f"{BASE_URL}/api/dewi/recruitment/candidates",
                              json={"name": f"TEST_Hired_{uid}", "email": f"hired_{uid}@example.com",
                                    "phone": "081234", "position": "Dev", "stage": "Offering",
                                    "source": "Manual", "job_id": job_id, "job_title": job_title}, headers=headers)
    assert create_r.status_code in [200, 201]
    cand_id = create_r.json()["candidate"]["candidate_id"]

    hire_r = requests.put(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}",
                           json={"stage": "Hired"}, headers=headers)
    assert hire_r.status_code == 200, f"Hire failed: {hire_r.text}"
    cand = hire_r.json().get("candidate", hire_r.json())

    checklist_id = cand.get("onboarding_checklist_id")
    assert checklist_id, f"onboarding_checklist_id not set. Candidate: {cand}"
    print(f"PASS: onboarding_checklist_id = {checklist_id}")

    logs = cand.get("email_logs", [])
    hired_log = next((entry for entry in logs if entry["stage"] == "Hired"), None)
    assert hired_log, f"Hired email log missing. Logs: {logs}"
    print(f"PASS: Hired email log: {hired_log['subject']}")

    cl_r = requests.get(f"{BASE_URL}/api/dewi/onboarding/checklists/{checklist_id}", headers=headers)
    assert cl_r.status_code == 200, f"Checklist {checklist_id} not found: {cl_r.text}"
    cl = cl_r.json().get("checklist", cl_r.json())
    print(f"PASS: Checklist accessible, tasks: {len(cl.get('tasks', []))}")

def test_onboarding_seed_creates_checklists(headers):
    """Muat Demo should create checklists (active employee filter)"""
    seed_r = requests.post(f"{BASE_URL}/api/dewi/onboarding/seed", headers=headers)
    assert seed_r.status_code == 200
    
    cl_r = requests.get(f"{BASE_URL}/api/dewi/onboarding/checklists", headers=headers)
    assert cl_r.status_code == 200
    data = cl_r.json()
    total = data.get("total", 0)
    assert total > 0, f"Seed created 0 checklists. Checklists response: {data}"
    print(f"PASS: {total} checklists found after seed")

def test_template_list_and_structure(headers):
    """Templates endpoint returns list with tasks"""
    r = requests.get(f"{BASE_URL}/api/dewi/onboarding/templates", headers=headers)
    assert r.status_code == 200
    templates = r.json().get("templates", [])
    assert len(templates) > 0, "No templates found"
    tpl = templates[0]
    assert "template_id" in tpl
    assert "tasks" in tpl
    tasks = tpl["tasks"]
    assert len(tasks) > 0, "Template has no tasks"
    task = tasks[0]
    assert "title" in task
    assert "day" in task
    assert "assigned_to" in task
    print(f"PASS: Template {tpl['template_id']} has {len(tasks)} tasks. Task keys: {list(task.keys())}")

def test_rejected_stage_email_log(headers):
    """Rejected stage creates email log"""
    uid = uuid.uuid4().hex[:6]
    create_r = requests.post(f"{BASE_URL}/api/dewi/recruitment/candidates",
                              json={"name": f"TEST_Rej_{uid}", "email": f"rej_{uid}@example.com",
                                    "phone": "081234", "position": "Dev", "stage": "Screening CV",
                                    "source": "Manual", "job_title": "Developer"}, headers=headers)
    assert create_r.status_code in [200, 201]
    cand_id = create_r.json()["candidate"]["candidate_id"]

    put_r = requests.put(f"{BASE_URL}/api/dewi/recruitment/candidates/{cand_id}",
                          json={"stage": "Rejected", "rejection_reason": "Tidak memenuhi kualifikasi"}, headers=headers)
    assert put_r.status_code == 200
    cand = put_r.json().get("candidate", put_r.json())
    logs = cand.get("email_logs", [])
    rej_log = next((entry for entry in logs if entry["stage"] == "Rejected"), None)
    assert rej_log, f"Rejected email log missing: {logs}"
    print(f"PASS: Rejected email log: {rej_log['subject']}")
