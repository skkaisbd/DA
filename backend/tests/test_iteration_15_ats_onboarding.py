"""
Iteration 15 - ATS (Rekrutmen) & Onboarding module tests
Tests: /api/dewi/recruitment/* and /api/dewi/onboarding/*
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json().get("token") or r.json().get("access_token")

@pytest.fixture(scope="module")
def auth(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ===== ATS / Recruitment =====

class TestATSJobs:
    """ATS Jobs CRUD"""

    def test_list_jobs(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/recruitment/jobs")
        assert r.status_code == 200
        data = r.json()
        jobs = data.get("jobs", data) if isinstance(data, dict) else data
        assert isinstance(jobs, list)
        print(f"PASS: list_jobs returned {len(jobs)} jobs")

    def test_create_job(self, auth):
        r = auth.post(f"{BASE_URL}/api/dewi/recruitment/jobs", json={
            "title": "TEST_Job_IT15",
            "department": "Testing",
            "location": "Remote",
            "type": "full_time",
            "status": "open",
            "description": "Test job iteration 15"
        })
        assert r.status_code == 200
        data = r.json()
        job = data.get("job", data) if isinstance(data, dict) else data
        assert job.get("title") == "TEST_Job_IT15"
        print(f"PASS: create_job id={job.get('id')}")

    def test_pipeline(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/recruitment/pipeline")
        assert r.status_code == 200
        data = r.json()
        assert "stages" in data or isinstance(data, dict)
        print(f"PASS: pipeline returned stages: {list(data.keys()) if isinstance(data, dict) else 'list'}")

    def test_analytics(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/recruitment/analytics")
        assert r.status_code == 200
        print("PASS: analytics endpoint works")


class TestATSCandidates:
    """ATS Candidates CRUD"""

    def test_list_candidates(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/recruitment/candidates")
        assert r.status_code == 200
        data = r.json()
        candidates = data.get("candidates", data) if isinstance(data, dict) else data
        assert isinstance(candidates, list)
        print(f"PASS: list_candidates returned {len(candidates)} candidates")

    def test_add_candidate(self, auth):
        r = auth.post(f"{BASE_URL}/api/dewi/recruitment/candidates", json={
            "name": "TEST_Candidate_IT15",
            "email": "test_it15@example.com",
            "phone": "08123456789",
            "position": "TEST_Job_IT15",
            "stage": "sourced"
        })
        assert r.status_code == 200
        data = r.json()
        candidate = data.get("candidate", data) if isinstance(data, dict) else data
        assert candidate.get("name") == "TEST_Candidate_IT15"
        print(f"PASS: add_candidate id={candidate.get('id')}")

    def test_seed(self, auth):
        r = auth.post(f"{BASE_URL}/api/dewi/recruitment/seed")
        assert r.status_code == 200
        print("PASS: seed endpoint works")


# ===== Onboarding =====

class TestOnboardingTemplates:
    """Onboarding template tests"""

    def test_list_templates(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/onboarding/templates")
        assert r.status_code == 200
        data = r.json()
        templates = data.get("templates", data) if isinstance(data, dict) else data
        assert isinstance(templates, list)
        print(f"PASS: list_templates returned {len(templates)} templates")

    def test_create_template(self, auth):
        r = auth.post(f"{BASE_URL}/api/dewi/onboarding/templates", json={
            "name": "TEST_Template_IT15",
            "dept": "Testing",
            "description": "Test template",
            "tasks": [],
            "duration_days": 30
        })
        assert r.status_code == 200
        data = r.json()
        template = data.get("template", data) if isinstance(data, dict) else data
        assert template.get("name") == "TEST_Template_IT15"
        print(f"PASS: create_template id={template.get('id')}")

    def test_seed_onboarding(self, auth):
        r = auth.post(f"{BASE_URL}/api/dewi/onboarding/seed")
        assert r.status_code == 200
        print("PASS: onboarding seed endpoint works")


class TestOnboardingChecklists:
    """Onboarding checklist tests"""

    def test_list_checklists(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/onboarding/checklists")
        assert r.status_code == 200
        data = r.json()
        checklists = data.get("checklists", data) if isinstance(data, dict) else data
        assert isinstance(checklists, list)
        print(f"PASS: list_checklists returned {len(checklists)} checklists")

    def test_create_checklist_and_add_task(self, auth):
        # Create checklist
        r = auth.post(f"{BASE_URL}/api/dewi/onboarding/checklists", json={
            "employee_name": "TEST_Employee_IT15",
            "employee_id": "TEST-EMP-IT15",
            "department": "Testing",
            "position": "Tester",
            "start_date": "2026-02-01"
        })
        assert r.status_code == 200
        data = r.json()
        checklist = data.get("checklist", data) if isinstance(data, dict) else data
        cid = checklist.get("id") or checklist.get("checklist_id")
        assert cid, f"No id in response: {data}"
        print(f"PASS: create_checklist id={cid}")

        # Add task with PIC and due_date fields
        r2 = auth.post(f"{BASE_URL}/api/dewi/onboarding/checklists/{cid}/tasks", json={
            "title": "TEST_Task_IT15",
            "description": "Test task with PIC and deadline",
            "assigned_to": "HR Manager",
            "due_date": "2026-02-15",
            "category": "admin"
        })
        assert r2.status_code == 200
        task_data = r2.json()
        task = task_data.get("task", task_data) if isinstance(task_data, dict) else task_data
        print(f"PASS: add_custom_task, due_date={task.get('due_date')}, assigned_to={task.get('assigned_to')}")

    def test_analytics(self, auth):
        r = auth.get(f"{BASE_URL}/api/dewi/onboarding/analytics")
        assert r.status_code == 200
        print("PASS: onboarding analytics works")
