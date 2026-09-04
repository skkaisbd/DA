"""
Session 17 Batch 1 — P2-16: AI Career Coach (Portal Saya)

Features:
- Comprehensive career coaching (path + skills + learning)
- Both one-time report + chat-based interaction
- Full data analysis (performance + skills + training + market + company needs)
- Emergent LLM integration
"""
import os
import uuid
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel
from database import get_db
from auth import require_auth
from ai_llm import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal-saya/career-coach", tags=["career-coach"])

LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")
LLM_MODEL = ("openai", "gpt-5.1")

# ============================================================================
# MODELS
# ============================================================================

class CareerCoachRequest(BaseModel):
    focus_area: Optional[str] = "overall"  # career_path, skills, learning, overall
    specific_goals: Optional[str] = None

class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[str] = None

# ============================================================================
# CAREER PROFILE ANALYSIS
# ============================================================================

@router.get("/profile")
async def get_career_profile(request: Request):
    """Get comprehensive career profile."""
    user = await require_auth(request)
    db = get_db()

    # Resolve employee via user_id → email fallback (same as dewi_portal_saya_hr)
    employee = await db.rahaza_employees.find_one(
        {"user_id": user.get("id"), "active": True}, {"_id": 0}
    )
    if not employee:
        email = (user.get("email") or "").lower()
        if email:
            employee = await db.rahaza_employees.find_one(
                {"email": email, "active": True}, {"_id": 0}
            )
    if not employee:
        raise HTTPException(404, "Data karyawan belum terhubung ke akun ini. Hubungi HR.")

    emp_id = employee["id"]
    profile = {
        "basic_info": {
            "name":          employee.get("name"),
            "employee_code": employee.get("employee_code"),
            "department":    employee.get("department"),
            "job_title":     employee.get("job_title"),
            "hire_date":     employee.get("contract_start_date") or employee.get("joined_at"),
            "tenure_years":  _calculate_tenure(employee.get("contract_start_date") or employee.get("joined_at")),
        },
        "current_skills":   employee.get("skills", []),
        "certifications":   employee.get("certifications", []),
        "education":        employee.get("education_level") or employee.get("education", "N/A"),
    }

    # LMS training history (via dewi_lms_enrollments)
    enrollments = await db.dewi_lms_enrollments.find(
        {"employee_id": emp_id}, {"_id": 0}
    ).sort("enrolled_at", -1).limit(10).to_list(10)
    course_ids = [e.get("course_id") for e in enrollments if e.get("course_id")]
    courses_map = {}
    if course_ids:
        async for c in db.dewi_lms_courses.find({"course_id": {"$in": course_ids}}, {"_id": 0}):
            courses_map[c["course_id"]] = c
    profile["training_history"] = [{
        "title":       courses_map.get(e.get("course_id"), {}).get("title", e.get("course_id")),
        "date":        e.get("completed_at") or e.get("enrolled_at"),
        "status":      e.get("status"),
        "passed":      e.get("passed"),
        "quiz_score":  e.get("quiz_score"),
    } for e in enrollments]

    # KPI history (last 6 months)
    kpi_results = await db.da_kpi_results.find(
        {"employee_id": emp_id, "kpi_final": {"$ne": None}},
        {"_id": 0, "kpi_final": 1, "grade": 1, "period_id": 1}
    ).sort("_id", -1).limit(6).to_list(6)
    profile["kpi_history"] = kpi_results

    # Career opportunities (open job postings)
    jobs = await db.dewi_recruitment_jobs.find(
        {"status": "open"}, {"_id": 0, "job_id": 1, "title": 1, "department": 1}
    ).limit(10).to_list(10)
    profile["available_opportunities"] = jobs

    return {"success": True, "data": profile}

def _calculate_tenure(hire_date_str: str) -> float:
    """Calculate tenure in years."""
    if not hire_date_str:
        return 0
    try:
        hire_date = datetime.fromisoformat(hire_date_str.replace('Z', '+00:00'))
        delta = datetime.now(timezone.utc) - hire_date
        return round(delta.days / 365.25, 1)
    except Exception:
        return 0

# ============================================================================
# AI CAREER REPORT GENERATION
# ============================================================================

@router.post("/generate-report")
async def generate_career_report(request: Request, coach_request: CareerCoachRequest):
    """Generate comprehensive AI career coaching report."""
    await require_auth(request)
    db = get_db()
    
    if not LLM_KEY:
        raise HTTPException(500, "AI service not configured")
    
    user = request.state.user
    
    # Get career profile
    profile_response = await get_career_profile(request)
    profile = profile_response["data"]
    
    # Build AI prompt
    prompt = _build_career_coaching_prompt(profile, coach_request)
    
    try:
        chat = LlmChat(
            api_key=LLM_KEY,
            session_id=f"career-report-{user.get('id')[:8]}",
            system_message="You are an expert career coach for employees in a garment manufacturing company. Provide comprehensive, actionable career guidance in Indonesian language."
        ).with_model(LLM_MODEL[0], LLM_MODEL[1])
        
        ai_response = await chat.send_message(UserMessage(text=prompt))
        ai_text = ai_response if isinstance(ai_response, str) else (ai_response.text if hasattr(ai_response, 'text') else str(ai_response))
        
        # Parse AI response into structured format
        report = _parse_ai_report(ai_text)
        
        # Save report
        report_doc = {
            "id": str(uuid.uuid4()),
            "employee_id": user.get("id"),
            "employee_name": profile["basic_info"]["name"],
            "focus_area": coach_request.focus_area,
            "report": report,
            "raw_ai_response": ai_text,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db["rahaza_career_reports"].insert_one(report_doc)
        
        # Remove MongoDB _id before returning
        report_doc.pop("_id", None)
        
        return {
            "success": True,
            "data": report_doc,
            "message": "Career coaching report generated"
        }
        
    except Exception as e:
        logger.error(f"AI career coaching error: {e}")
        raise HTTPException(500, f"AI generation failed: {str(e)}")

def _build_career_coaching_prompt(profile: dict, request: CareerCoachRequest) -> str:
    """Build comprehensive AI prompt."""
    return f"""You are an expert career coach for employees in a garment manufacturing company.

EMPLOYEE PROFILE:
- Name: {profile['basic_info']['name']}
- Current Role: {profile['basic_info']['job_title']} in {profile['basic_info']['department']}
- Tenure: {profile['basic_info']['tenure_years']} years
- Skills: {', '.join(profile['current_skills']) if profile['current_skills'] else 'Not specified'}
- Education: {profile['basic_info'].get('education', 'N/A')}

PERFORMANCE HISTORY:
{json.dumps(profile.get('performance_history', []), indent=2)}

TRAINING HISTORY:
{json.dumps(profile.get('training_history', []), indent=2)}

AVAILABLE OPPORTUNITIES:
{json.dumps(profile.get('available_opportunities', []), indent=2)}

FOCUS AREA: {request.focus_area}
{f"SPECIFIC GOALS: {request.specific_goals}" if request.specific_goals else ""}

Please provide a comprehensive career coaching report covering:
1. CURRENT ASSESSMENT: Strengths, areas for improvement, market positioning
2. CAREER PATH RECOMMENDATIONS: Short-term (1 year), Mid-term (3 years), Long-term (5+ years)
3. SKILL DEVELOPMENT PLAN: Critical skills to develop, recommended trainings/certifications
4. LEARNING RESOURCES: Specific courses, books, mentorship opportunities
5. ACTION PLAN: Concrete steps with timeline (monthly breakdown for next 6 months)
6. OPPORTUNITIES ANALYSIS: Which internal job openings match their profile and how to prepare

Format the response in clear sections with actionable insights."""

def _parse_ai_report(ai_text: str) -> dict:
    """Parse AI response into structured report."""
    # Simplified parsing - in production, could use more sophisticated NLP
    return {
        "full_report": ai_text,
        "summary": ai_text[:500] + "..." if len(ai_text) > 500 else ai_text,
        "sections": _extract_sections(ai_text)
    }

def _extract_sections(text: str) -> dict:
    """Extract sections from AI text."""
    sections = {}
    current_section = "introduction"
    current_content = []
    
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        
        # Detect section headers (all caps or numbered)
        if line.isupper() or (line[0].isdigit() and '.' in line[:5]):
            if current_content:
                sections[current_section] = '\n'.join(current_content)
            current_section = line.lower().replace(':', '').strip()
            current_content = []
        else:
            current_content.append(line)
    
    if current_content:
        sections[current_section] = '\n'.join(current_content)
    
    return sections

# ============================================================================
# CHAT-BASED COACHING
# ============================================================================

@router.post("/chat")
async def chat_with_coach(request: Request, chat_msg: ChatMessage):
    """Interactive chat with AI career coach."""
    await require_auth(request)
    db = get_db()
    
    if not LLM_KEY:
        raise HTTPException(500, "AI service not configured")
    
    user = request.state.user
    
    # Get or create conversation
    conversation_id = chat_msg.conversation_id or str(uuid.uuid4())
    
    conversation = await db["rahaza_career_chats"].find_one({"id": conversation_id})
    
    if not conversation:
        # Get profile for context
        profile_response = await get_career_profile(request)
        profile = profile_response["data"]
        
        system_prompt = f"""You are a supportive career coach helping {profile['basic_info']['name']}, 
a {profile['basic_info']['job_title']} with {profile['basic_info']['tenure_years']} years tenure. 
Provide personalized, actionable career guidance."""
        
        conversation = {
            "id": conversation_id,
            "employee_id": user.get("id"),
            "messages": [],
            "system_prompt": system_prompt,
            "started_at": datetime.now(timezone.utc).isoformat()
        }
    
    # Add user message
    conversation["messages"].append({
        "role": "user",
        "content": chat_msg.message,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    try:
        # Build conversation context
        conversation_context = ""
        if conversation.get("system_prompt"):
            conversation_context = conversation["system_prompt"] + "\n\n"
        
        # Add conversation history (last 10 messages)
        for msg in conversation["messages"][-10:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation_context += f"{role}: {msg['content']}\n"
        
        conversation_context += f"User: {chat_msg.message}\n"
        
        # Call AI
        chat = LlmChat(
            api_key=LLM_KEY,
            session_id=conversation_id,
            system_message=conversation.get("system_prompt", "You are a supportive career coach.")
        ).with_model(LLM_MODEL[0], LLM_MODEL[1])
        
        ai_response = await chat.send_message(UserMessage(text=chat_msg.message))
        ai_text = ai_response if isinstance(ai_response, str) else (ai_response.text if hasattr(ai_response, 'text') else str(ai_response))
        
        # Add AI response
        conversation["messages"].append({
            "role": "assistant",
            "content": ai_text,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        conversation["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Save conversation
        await db["rahaza_career_chats"].replace_one(
            {"id": conversation_id},
            conversation,
            upsert=True
        )
        
        return {
            "success": True,
            "data": {
                "conversation_id": conversation_id,
                "message": ai_text,
                "timestamp": conversation["messages"][-1]["timestamp"]
            }
        }
        
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        raise HTTPException(500, f"AI chat failed: {str(e)}")

@router.get("/chat/history")
async def get_chat_history(request: Request, conversation_id: Optional[str] = Query(None)):
    """Get chat conversation history."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    
    if conversation_id:
        conversation = await db["rahaza_career_chats"].find_one({"id": conversation_id})
        if not conversation:
            raise HTTPException(404, "Conversation not found")
        
        conversation.pop("_id", None)
        return {
            "success": True,
            "data": conversation
        }
    else:
        # List all conversations
        conversations = await db["rahaza_career_chats"].find(
            {"employee_id": user.get("id")}
        ).sort("updated_at", -1).limit(20).to_list(length=20)
        
        for c in conversations:
            c.pop("_id", None)
            # Only include summary
            c["message_count"] = len(c.get("messages", []))
            c["last_message"] = c["messages"][-1] if c.get("messages") else None
            c.pop("messages", None)  # Don't send full history in list view
        
        return {
            "success": True,
            "data": conversations
        }

# ============================================================================
# REPORT HISTORY
# ============================================================================

@router.get("/reports")
async def get_report_history(request: Request, limit: int = Query(10, ge=1, le=200)):
    """Get user's career report history."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    
    reports = await db["rahaza_career_reports"].find(
        {"employee_id": user.get("id")}
    ).sort("generated_at", -1).limit(limit).to_list(length=limit)
    
    for r in reports:
        r.pop("_id", None)
    
    return {
        "success": True,
        "data": reports
    }
