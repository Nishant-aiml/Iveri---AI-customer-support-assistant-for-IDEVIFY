from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.chat import ChatMessageResponse

class DashboardStatsResponse(BaseModel):
    total_chats: int = Field(0, description="Total number of customer chat sessions")
    total_questions: int = Field(0, description="Total questions asked by customers")
    answered_count: int = Field(0, description="Questions successfully answered from knowledge base")
    unanswered_count: int = Field(0, description="Questions flagged as unanswered/missing info")
    resolution_rate: float = Field(0.0, description="Percentage of answered questions (0.0 to 100.0)")
    avg_latency_ms: float = Field(0.0, description="Average response latency in milliseconds")
    thumbs_up_count: int = Field(0, description="Positive customer feedback votes")
    thumbs_down_count: int = Field(0, description="Negative customer feedback votes")
    total_documents: int = Field(0, description="Total knowledge base documents uploaded")
    indexed_chunks: int = Field(0, description="Total active vector/sparse text chunks")

class UnansweredQuestionItem(BaseModel):
    id: str
    session_id: Optional[str] = None
    question_text: str
    customer_email: Optional[str] = None
    top_retrieval_score: float = 0.0
    is_resolved: bool = False
    resolved_answer: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime

class ResolveQuestionRequest(BaseModel):
    answer_text: str = Field(..., min_length=3, description="Ground truth answer provided by business owner")

class ResolveQuestionResponse(BaseModel):
    status: str
    unanswered_id: str
    is_resolved: bool
    document_id: str
    chunks_created: int
    message: str

class PlaygroundTestRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Question to test against the knowledge base")

class PlaygroundChunkDetail(BaseModel):
    chunk_id: str
    document_name: str
    page_number: int
    text_excerpt: str
    score: float
    retrieval_type: str

class PlaygroundTestResponse(BaseModel):
    query: str
    circuit_breaker_passed: bool
    circuit_breaker_reason: str
    retrieved_chunks: List[PlaygroundChunkDetail]
    top_confidence: float
    generated_answer: str
    llm_provider: str
    latency_ms: int
    laya_intent: Optional[str] = "store_support"

class ChatSessionSummary(BaseModel):
    session_id: str
    channel: str
    customer_email: Optional[str] = None
    sentiment: str = "neutral"
    primary_topic: str = "general"
    share_url: Optional[str] = None
    started_at: datetime
    message_count: int
    has_downvote: bool
    messages: List[ChatMessageResponse] = []

class SentimentBreakdown(BaseModel):
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    positive_pct: float = 0.0
    neutral_pct: float = 0.0
    negative_pct: float = 0.0

class TopicCount(BaseModel):
    topic: str
    count: int
    percentage: float

class DailyTrendItem(BaseModel):
    date: str
    total_queries: int = 0
    answered: int = 0
    unanswered: int = 0
    positive: int = 0
    negative: int = 0

class ResolutionFunnel(BaseModel):
    total_sessions: int = 0
    total_queries: int = 0
    ai_resolved: int = 0
    human_followup_needed: int = 0
    resolution_rate: float = 0.0

class LatencySummary(BaseModel):
    avg_ms: float = 0.0
    min_ms: int = 0
    max_ms: int = 0
    sub_second_pct: float = 0.0

class BusinessAnalyticsResponse(BaseModel):
    total_queries: int = 0
    sentiment_breakdown: SentimentBreakdown
    top_topics: List[TopicCount] = []
    daily_trend: List[DailyTrendItem] = []
    funnel: ResolutionFunnel
    latency_metrics: LatencySummary
