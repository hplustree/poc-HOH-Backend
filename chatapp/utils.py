from budget.models import Projects, ProjectCosts, ProjectOverheads
from chatapp.models import Session, Conversation, Messages, UpdatedCost
from news.models import Alert
from collections import defaultdict
import requests
import json


def generate_costing_json_from_db(project_id=None, include_wrapper=False):
    """
    Unified function to generate costing_json from database with latest data.
    
    Args:
        project_id: Specific project ID, if None uses latest project
        include_wrapper: If True, returns {"status": "success", "data": {...}}, 
                        if False returns direct format {"project": {...}, ...}
    
    Returns:
        Dictionary with costing_json structure
    """
    try:
        # Get project - either specific or latest
        if project_id:
            project = Projects.objects.get(id=project_id)
        else:
            project = Projects.objects.order_by('-updated_at').first()
            
        if not project:
            return {"status": "error", "message": "No project found"}
        
        # Get all cost line items for this project
        project_costs = ProjectCosts.objects.filter(project=project).order_by('category_code', 'id')
        
        # Calculate category totals properly
        category_totals = defaultdict(float)
        cost_line_items = []
        
        for cost in project_costs:
            category_totals[cost.category_code] += float(cost.line_total)
        
        # Build cost line items with correct category totals
        for cost in project_costs:
            line_item = {
                "category_code": cost.category_code,
                "category_name": cost.category_name,
                "item_description": cost.item_description,
                "supplier_brand": cost.supplier_brand or "",
                "unit": cost.unit or "",
                "quantity": float(cost.quantity),
                "rate_per_unit": float(cost.rate_per_unit),
                "line_total": float(cost.line_total),
                "category_total": category_totals[cost.category_code]
            }
            cost_line_items.append(line_item)
        
        # Get overheads for this project
        overheads = []
        project_overheads = ProjectOverheads.objects.filter(project=project)
        
        if project_overheads.exists():
            for overhead in project_overheads:
                overheads.append({
                    "overhead_type": overhead.overhead_type,
                    "description": overhead.description or "Provided in your BOQ",
                    "basis": overhead.basis or "On total cost",
                    "percentage": float(overhead.percentage),
                    "amount": float(overhead.amount)
                })
        else:
            # Add default overheads if none exist
            subtotal = sum(float(cost.line_total) for cost in project_costs)
            overheads = [
                {
                    "overhead_type": "Contingency",
                    "description": "Provided in your BOQ",
                    "basis": "On total cost",
                    "percentage": 10.0,
                    "amount": round(subtotal * 0.10, 2)
                },
                {
                    "overhead_type": "Contractor Margin",
                    "description": "Provided in your BOQ",
                    "basis": "On total cost",
                    "percentage": 10.0,
                    "amount": round(subtotal * 0.10, 2)
                }
            ]
        
        # Calculate total cost
        subtotal = sum(item["line_total"] for item in cost_line_items)
        overhead_total = sum(item["amount"] for item in overheads)
        total_cost = subtotal + overhead_total
        
        # Use stored total_cost if available, otherwise use calculated
        if project.total_cost is not None:
            total_cost = float(project.total_cost)
        
        # Build the costing data
        costing_data = {
            "project": {
                "name": project.name,
                "location": project.location or "",
                "total_cost": int(total_cost),
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "end_date": project.end_date.isoformat() if project.end_date else None
            },
            "cost_line_items": cost_line_items,
            "overheads": overheads
        }
        
        # Return with or without wrapper based on parameter
        if include_wrapper:
            return {
                "status": "success",
                "source": f"{project.name}_project_data.pdf",
                "data": costing_data
            }
        else:
            return costing_data
            
    except Projects.DoesNotExist:
        return {"status": "error", "message": "Project not found"}
    except Exception as e:
        return {"status": "error", "message": f"Error generating costing data: {str(e)}"}


def get_project_costing_json(project_id):
    """
    Build costing JSON from project data in the database matching the required format.
    This function maintains backward compatibility by returning the wrapped format.
    """
    return generate_costing_json_from_db(project_id=project_id, include_wrapper=True)


def get_previous_chat_history(conversation_id, limit=10):
    """
    Get previous chat history formatted for external API
    """
    try:
        conversation = Conversation.objects.get(conversation_id=conversation_id)
        messages = Messages.objects.filter(
            conversation=conversation
        ).order_by('created_at')[:limit * 2]  # Get both user and AI messages
        
        previous_chat = {}
        chat_pair_count = 1
        current_pair = {}
        
        for message in messages:
            if message.message_type == 'user':
                current_pair['Human'] = message.content
            elif message.message_type == 'assistant':
                current_pair['AI'] = message.content
                
                # If we have both Human and AI messages, add to previous_chat
                if 'Human' in current_pair and 'AI' in current_pair:
                    previous_chat[str(chat_pair_count)] = {
                        "Human": current_pair['Human'],
                        "AI": current_pair['AI']
                    }
                    chat_pair_count += 1
                    current_pair = {}
        
        return previous_chat
        
    except Conversation.DoesNotExist:
        return {}


def get_accepted_decisions():
    """
    Get accepted decisions from Alert model where is_accept = True
    """
    try:
        accepted_alerts = Alert.objects.filter(is_accept=True).order_by('-accepted_at')
        
        previous_decisions = {}
        decision_count = 1
        
        for alert in accepted_alerts:
            decision_data = {
                "decision": alert.decision,
                "reason": alert.reason,
                "suggestion": alert.suggestion,
                "category_name": alert.category_name,
                "item": alert.item,
                "old_supplier_brand": str(alert.old_supplier_brand) if alert.old_supplier_brand else "",
                "old_rate_per_unit": float(alert.old_rate_per_unit) if alert.old_rate_per_unit else 0,
                "new_supplier_brand": str(alert.new_supplier_brand) if alert.new_supplier_brand else "",
                "new_rate_per_unit": float(alert.new_rate_per_unit) if alert.new_rate_per_unit else 0,
                "cost_impact": float(alert.cost_impact) if alert.cost_impact else 0,
                "accepted_at": alert.accepted_at.isoformat() if alert.accepted_at else None
            }
            previous_decisions[str(decision_count)] = decision_data
            decision_count += 1
        
        return previous_decisions
        
    except Exception as e:
        print(f"Error fetching accepted decisions: {str(e)}")
        return {}


def build_api_payload(question, session_id, conversation_id=None):
    """
    Build the complete payload for the external API
    """
    try:
        session = Session.objects.get(session_id=session_id)
        project_id = session.project_id.id
        
        # Get costing JSON from project data
        costing_json = get_project_costing_json(project_id)
        # Get previous chat history if conversation exists
        previous_chat = {}
        if conversation_id:
            previous_chat = get_previous_chat_history(conversation_id)
        
        # Get accepted decisions from Alert model
        previous_decisions = get_accepted_decisions()
        
        # Build the payload
        payload = {
            "question": question,
            "previous_chat": previous_chat,
            "previous_decision": previous_decisions,
            "costing_json": costing_json
        }
        
        return payload
        
    except Session.DoesNotExist:
        raise ValueError("Session not found")


def send_to_external_api(payload, api_url="http://0.0.0.0:8000/api/chatbot"):
    """
    Send the payload to external API and return response
    """
    try:
        headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            api_url,
            headers=headers,
            data=json.dumps(payload),
            timeout=300
        )
        
        if response.status_code == 200:
            return {
                "success": True,
                "data": response.json()
            }
        else:
            return {
                "success": False,
                "error": f"API returned status {response.status_code}",
                "details": response.text
            }
            
    except requests.RequestException as e:
        return {
            "success": False,
            "error": "Failed to connect to external API",
            "details": str(e)
        }


def save_message_to_db(conversation_id, sender_id, message_type, content, metadata=None):
    """
    Save a message to the database
    """
    try:
        conversation = Conversation.objects.get(conversation_id=conversation_id)
        
        message = Messages.objects.create(
            conversation=conversation,
            sender_id=sender_id if sender_id else None,
            message_type=message_type,
            content=content,
            metadata=metadata or {}
        )
        
        return message
        
    except Conversation.DoesNotExist:
        raise ValueError("Conversation not found")


def save_updated_cost_to_db(conversation_id, message_id, costing_data, raw_response):
    """
    Save updated costing data from chatbot response to UpdatedCost table
    """
    try:
        conversation = Conversation.objects.get(conversation_id=conversation_id)
        message = Messages.objects.get(message_id=message_id) if message_id else None
        
        # Extract project data
        project_data = costing_data.get('data', {}).get('project', {})
        cost_line_items = costing_data.get('data', {}).get('cost_line_items', [])
        overheads = costing_data.get('data', {}).get('overheads', [])
        
        # Parse dates if they exist
        start_date = None
        end_date = None
        if project_data.get('start_date'):
            try:
                start_date = timezone.datetime.fromisoformat(project_data['start_date']).date()
            except:
                pass
        if project_data.get('end_date'):
            try:
                end_date = timezone.datetime.fromisoformat(project_data['end_date']).date()
            except:
                pass
        
        # Create UpdatedCost record
        updated_cost = UpdatedCost.objects.create(
            conversation=conversation,
            message=message,
            project_name=project_data.get('name', ''),
            project_location=project_data.get('location', ''),
            total_cost=project_data.get('total_cost'),
            start_date=start_date,
            end_date=end_date,
            cost_line_items=cost_line_items,
            overheads=overheads,
            raw_costing_response=raw_response,
            is_accept=None  # Default to null, user will decide later
        )
        
        return updated_cost
        
    except (Conversation.DoesNotExist, Messages.DoesNotExist) as e:
        raise ValueError(f"Database record not found: {str(e)}")
    except Exception as e:
        raise ValueError(f"Error saving updated cost: {str(e)}")
