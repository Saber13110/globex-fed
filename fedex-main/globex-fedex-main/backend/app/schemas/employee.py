from datetime import datetime

from pydantic import BaseModel, Field


class EmployeeDashboardStats(BaseModel):
    open_tickets: int
    pending_tickets: int
    total_clients: int
    unread_notifications: int
    unread_admin_messages: int
    recent_trackings: int
    active_clients: int = 0
    tracking_exceptions: int = 0
    pending_escalations: int = 0
    documents_processed: int = 0
    pending_actions: int = 0
    unread_tickets: int = 0


class EmployeeMetricCard(BaseModel):
    key: str
    value: int
    label: str
    trend: str
    trend_up: bool
    icon: str


class EmployeeDashboardClientWidget(BaseModel):
    id: int
    full_name: str
    company: str
    email: str
    last_activity: str
    avatar_initials: str
    open_tickets: int = 0


class EmployeeDashboardTicketWidget(BaseModel):
    id: int
    ticket_number: str
    subject: str
    priority: str
    status: str
    client_name: str
    created_at: datetime


class EmployeeDashboardTrackingEvent(BaseModel):
    tracking_number: str
    status: str
    client_name: str
    created_at: datetime
    is_exception: bool = False


class EmployeeDashboardTrackingSummary(BaseModel):
    delayed_count: int
    exception_count: int
    active_count: int
    latest_events: list[EmployeeDashboardTrackingEvent]


class EmployeeDashboardAdminComm(BaseModel):
    unread_count: int
    latest_message: str
    latest_sender: str
    latest_at: datetime | None = None
    latest_announcement: str = ""


class EmployeeNotificationRead(BaseModel):
    id: int
    type: str
    kind: str
    title: str
    message: str
    status: str
    link: str
    is_read: bool
    related_ticket_id: int | None = None
    related_tracking_number: str = ""
    related_document_id: int | None = None
    related_client_id: int | None = None
    created_at: datetime
    read_at: datetime | None = None


class EmployeeNotificationStats(BaseModel):
    all: int
    unread: int
    support: int
    tracking: int
    documents: int
    security: int


class EmployeeDashboardWorkspace(BaseModel):
    stats: EmployeeDashboardStats
    metrics: list[EmployeeMetricCard]
    recent_clients: list[EmployeeDashboardClientWidget]
    recent_tickets: list[EmployeeDashboardTicketWidget]
    tracking_summary: EmployeeDashboardTrackingSummary
    admin_communication: EmployeeDashboardAdminComm
    recent_notifications: list[EmployeeNotificationRead]


class EmployeeSearchHit(BaseModel):
    kind: str
    id: str
    title: str
    subtitle: str
    link: str


class EmployeeSearchResponse(BaseModel):
    query: str
    items: list[EmployeeSearchHit]


class EmployeeClientSummary(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    preferred_language: str
    created_at: datetime
    open_tickets: int = 0
    recent_trackings: int = 0
    documents_count: int = 0
    company: str = ""
    avatar_initials: str = ""
    last_activity: str = ""
    pending_issues: int = 0
    active_shipments: int = 0


class EmployeeClientOpsStats(BaseModel):
    total_clients: int
    active_clients: int
    open_tickets: int
    active_shipments: int
    recent_documents: int
    pending_issues: int
    metrics: list[EmployeeMetricCard]


class EmployeeClientActivityEvent(BaseModel):
    id: str
    kind: str
    title: str
    description: str
    created_at: datetime


class EmployeeClientListResponse(BaseModel):
    items: list[EmployeeClientSummary]
    total: int
    page: int = 1
    limit: int = 12
    total_pages: int = 1


class EmployeeClientDetail(BaseModel):
    id: int
    full_name: str
    email: str
    status: str
    preferred_language: str
    organization_id: str
    created_at: datetime
    open_tickets: int
    total_trackings: int
    total_documents: int
    company: str = ""
    avatar_initials: str = ""
    last_login: datetime | None = None
    last_activity: str = ""
    pending_issues: int = 0
    active_shipments: int = 0
    assigned_employee: str = ""
    resolved_tickets: int = 0


class EmployeeTrackingItem(BaseModel):
    id: int
    tracking_number: str
    status: str
    current_location: str
    estimated_delivery: str
    user_question: str
    created_at: datetime
    client_name: str | None = None
    client_id: int | None = None
    status_category: str = "pending"
    is_exception: bool = False


class EmployeeShipmentTimelineEvent(BaseModel):
    id: str
    date: str
    time: str
    location: str
    description: str
    kind: str


class EmployeeShipmentMapPoint(BaseModel):
    label: str
    lat: float
    lng: float
    kind: str


class EmployeeShipmentExceptionInfo(BaseModel):
    exception_type: str
    reason: str
    priority: str
    detected_at: datetime | None = None


class EmployeeShipmentRelatedClient(BaseModel):
    id: int
    full_name: str
    email: str
    avatar_initials: str = ""
    trackings_count: int = 0
    tickets_count: int = 0
    documents_count: int = 0


class EmployeeShipmentHealth(BaseModel):
    status: str
    risk: str
    exception: bool = False
    pod: bool = False


class EmployeeShipmentDetail(BaseModel):
    tracking_number: str
    status: str
    status_category: str
    current_location: str
    recipient: str
    last_update: str
    estimated_delivery: str
    reference_number: str
    service_type: str
    weight: str
    dimensions: str
    sender: str
    destination: str
    client_id: int | None = None
    client_name: str = ""
    client_email: str = ""
    timeline: list[EmployeeShipmentTimelineEvent]
    map_points: list[EmployeeShipmentMapPoint]
    exception: EmployeeShipmentExceptionInfo | None = None
    pod_available: bool = False
    related_client: EmployeeShipmentRelatedClient | None = None
    health: EmployeeShipmentHealth | None = None


class EmployeeShipmentListResponse(BaseModel):
    items: list[EmployeeTrackingItem]
    total: int
    page: int = 1
    limit: int = 12
    total_pages: int = 1


class EmployeeTrackingOpsStats(BaseModel):
    active_shipments: int
    delayed_count: int
    exception_count: int
    total_trackings: int
    metrics: list[EmployeeMetricCard]


class EmployeeDocumentItem(BaseModel):
    id: str
    title: str
    doc_type: str
    tracking_number: str
    client_name: str
    client_id: int
    created_at: datetime


class EmployeeAdminMessageRead(BaseModel):
    id: int
    sender_role: str
    sender_name: str | None = None
    body: str
    attachment_url: str | None = None
    is_read: bool
    created_at: datetime


class EmployeeAdminChatResponse(BaseModel):
    items: list[EmployeeAdminMessageRead]
    unread_count: int


class AdminEmployeeChatListItem(BaseModel):
    id: int
    full_name: str
    email: str
    avatar_initial: str
    unread_count: int = 0
    last_message: str = ""
    last_message_at: datetime | None = None


class EmployeeAdminChatParticipant(BaseModel):
    id: str
    name: str
    role: str
    avatar_initial: str
    online: bool = True
    email: str = ""


class EmployeeAdminChatSharedFile(BaseModel):
    id: int
    name: str
    url: str
    mime_type: str = ""
    uploaded_at: datetime
    uploaded_by: str


class EmployeeAdminChatConversation(BaseModel):
    id: str
    name: str
    role: str
    avatar_initial: str
    online: bool = True
    last_message: str = ""
    last_message_at: datetime | None = None
    unread_count: int = 0


class EmployeeAdminChatWorkspace(BaseModel):
    conversations: list[EmployeeAdminChatConversation]
    messages: list[EmployeeAdminMessageRead]
    participants: list[EmployeeAdminChatParticipant]
    shared_files: list[EmployeeAdminChatSharedFile]
    unread_count: int
    created_at: datetime | None = None
    last_activity_at: datetime | None = None


class EmployeeAdminChatSearchHit(BaseModel):
    kind: str
    id: str
    title: str
    subtitle: str
    message_id: int | None = None


class EmployeeAdminChatSearchResponse(BaseModel):
    query: str
    items: list[EmployeeAdminChatSearchHit]


class EmployeeAdminChatTyping(BaseModel):
    active: bool = True


class EmployeeAdminMessageCreate(BaseModel):
    body: str = Field(default="", max_length=4000)
    attachment_url: str | None = None


class EmployeeNotificationListResponse(BaseModel):
    items: list[EmployeeNotificationRead]
    unread_count: int
    total: int = 0
    page: int = 1
    limit: int = 20
    total_pages: int = 1


class EmployeeSettingsRead(BaseModel):
    full_name: str
    email: str
    preferred_language: str
    response_preferences: str


class EmployeeSettingsUpdate(BaseModel):
    full_name: str | None = None
    preferred_language: str | None = None
    response_preferences: str | None = None


class EmployeeAiRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class EmployeeAiClientResult(BaseModel):
    id: int
    full_name: str
    email: str
    company: str
    open_tickets: int
    total_trackings: int
    total_documents: int


class EmployeeAiTrackingEvent(BaseModel):
    label: str
    at: str


class EmployeeAiTrackingResult(BaseModel):
    tracking_number: str
    status: str
    current_location: str
    estimated_delivery: str
    is_exception: bool
    client_name: str = ""
    events: list[EmployeeAiTrackingEvent] = []


class EmployeeAiTicketResult(BaseModel):
    id: int
    ticket_number: str
    subject: str
    priority: str
    status: str
    client_name: str


class EmployeeAiDocumentResult(BaseModel):
    id: str
    title: str
    doc_type: str
    created_at: datetime
    client_name: str
    tracking_number: str = ""


class EmployeeAiAction(BaseModel):
    label: str
    route: str
    kind: str


class EmployeeAiResponse(BaseModel):
    reply: str
    intent: str = "general"
    context_used: bool = False
    clients: list[EmployeeAiClientResult] = []
    tracking: EmployeeAiTrackingResult | None = None
    tickets: list[EmployeeAiTicketResult] = []
    documents: list[EmployeeAiDocumentResult] = []
    admin_draft: str | None = None
    actions: list[EmployeeAiAction] = []


class EmployeeAiAgentMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversationId: str | None = None


class EmployeeAiAgentCardAction(BaseModel):
    label: str
    route: str


class EmployeeAiAgentCard(BaseModel):
    type: str
    title: str
    subtitle: str = ""
    meta: dict = Field(default_factory=dict)
    actions: list[EmployeeAiAgentCardAction] = Field(default_factory=list)


class EmployeeAiAgentMessageResponse(BaseModel):
    reply: str
    intent: str = "general_question"
    conversationId: str
    cards: list[EmployeeAiAgentCard] = Field(default_factory=list)
    actions: list[EmployeeAiAction] = Field(default_factory=list)
    createdAt: datetime | None = None


class EmployeeAiAgentMessageRead(BaseModel):
    id: int
    role: str
    content: str
    intent: str = ""
    cards: list[EmployeeAiAgentCard] = Field(default_factory=list)
    created_at: datetime


class EmployeeAiAgentConversationSummary(BaseModel):
    id: str
    title: str
    preview: str = ""
    group: str = "today"
    created_at: datetime
    updated_at: datetime


class EmployeeAiAgentConversationDetail(BaseModel):
    id: str
    title: str
    messages: list[EmployeeAiAgentMessageRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class EmployeeAiAgentConversationCreate(BaseModel):
    title: str = Field(default="New conversation", max_length=200)


class EmployeeAiAgentConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class EmployeeAiAgentLiveContext(BaseModel):
    recent_clients: list[EmployeeDashboardClientWidget] = Field(default_factory=list)
    recent_shipments: list[EmployeeDashboardTrackingEvent] = Field(default_factory=list)
    recent_tickets: list[EmployeeDashboardTicketWidget] = Field(default_factory=list)
    pending_documents: list[EmployeeAiDocumentResult] = Field(default_factory=list)
    tracking_exceptions: list[EmployeeDashboardTrackingEvent] = Field(default_factory=list)
    unread_notification_count: int = 0
    unread_admin_count: int = 0


class EmployeeChatContextPanel(BaseModel):
    recent_clients: list[EmployeeDashboardClientWidget]
    recent_tickets: list[EmployeeDashboardTicketWidget]
    tracking_exceptions: list[EmployeeDashboardTrackingEvent]
    unread_notifications: list[EmployeeNotificationRead]
    admin_messages: list[EmployeeAdminMessageRead]
    unread_admin_count: int = 0
    unread_notification_count: int = 0


class EmployeeHelpdeskMessageRead(BaseModel):
    id: int
    author_role: str
    body: str
    attachment_url: str | None = None
    created_at: datetime
    author_name: str | None = None
    is_internal: bool = False


class EmployeeHelpdeskTicketSummary(BaseModel):
    id: int
    ticket_number: str
    subject: str
    category: str
    priority: str
    status: str
    customer_name: str
    customer_email: str
    client_id: int
    last_activity: str
    last_activity_at: datetime
    unread: bool
    tracking_number: str = ""
    assigned_employee: str = ""
    assigned_employee_id: int | None = None
    created_at: datetime
    updated_at: datetime | None = None


class EmployeeHelpdeskTicketListResponse(BaseModel):
    items: list[EmployeeHelpdeskTicketSummary]
    total: int = 0


class EmployeeHelpdeskTicketDetail(BaseModel):
    id: int
    ticket_number: str
    subject: str
    message: str
    category: str
    priority: str
    status: str
    attachment_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    customer_name: str
    customer_email: str
    client_id: int
    tracking_number: str = ""
    assigned_employee: str = ""
    assigned_employee_id: int | None = None
    messages: list[EmployeeHelpdeskMessageRead] = []


class EmployeeHelpdeskStats(BaseModel):
    open: int
    pending: int
    resolved: int
    closed: int
    escalated: int = 0
    unread: int
    total_active: int = 0


class EmployeeHelpdeskAssign(BaseModel):
    employee_id: int | None = None


class EmployeeHelpdeskInternalNote(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    attachmentUrl: str | None = Field(default=None, max_length=512)


class EmployeeHelpdeskEmployeeOption(BaseModel):
    id: int
    full_name: str
    email: str
