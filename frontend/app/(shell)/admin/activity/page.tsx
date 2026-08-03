"use client";

import { useState } from "react";
import { useConversation, useConversations } from "@/hooks/use-data";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { conversationStatus, formatDateTime } from "@/lib/format";

export default function AdminActivityPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const conversations = useConversations();
  const conversation = useConversation(selected);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">会话活动</h1>
        <p className="text-sm text-muted-foreground">所有客户会话与消息记录。</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardContent className="p-0">
            {conversations.isLoading && <LoadingState rows={6} />}
            {conversations.isError && (
              <ErrorState error={conversations.error} onRetry={() => conversations.refetch()} />
            )}
            {conversations.data && conversations.data.conversations.length === 0 && (
              <div className="p-4">
                <EmptyState title="暂无会话" />
              </div>
            )}
            {conversations.data && conversations.data.conversations.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>主题</TableHead>
                    <TableHead>渠道</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>时间</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {conversations.data.conversations.map((conversation) => (
                    <TableRow
                      key={conversation.conversation_id}
                      className={conversation.conversation_id === selected ? "bg-muted/50" : ""}
                      onClick={() => setSelected(conversation.conversation_id)}
                    >
                      <TableCell className="max-w-48 truncate font-medium">
                        {conversation.subject}
                      </TableCell>
                      <TableCell>{conversation.channel}</TableCell>
                      <TableCell>
                        <StatusBadge
                          value={conversation.status}
                          label={conversationStatus(conversation.status)}
                        />
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {formatDateTime(conversation.started_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            {!selected && (
              <p className="py-12 text-center text-sm text-muted-foreground">
                点击左侧会话查看消息记录。
              </p>
            )}
            {selected && conversation.isLoading && <LoadingState rows={4} />}
            {selected && conversation.isError && <ErrorState error={conversation.error} />}
            {selected && conversation.data && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold">{conversation.data.conversation.subject}</h3>
                  <StatusBadge
                    value={conversation.data.conversation.status}
                    label={conversationStatus(conversation.data.conversation.status)}
                  />
                </div>
                {conversation.data.messages.length === 0 ? (
                  <p className="py-8 text-center text-sm text-muted-foreground">暂无消息</p>
                ) : (
                  <ul className="space-y-3">
                    {conversation.data.messages.map((message) => (
                      <li key={message.message_id} className="rounded-md border border-border p-3">
                        <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
                          <span className="font-medium text-foreground">
                            {message.author_type === "agent" ? "Agent" : "用户"}
                          </span>
                          <span>{message.role}</span>
                          <span className="ml-auto">{formatDateTime(message.created_at)}</span>
                        </div>
                        <p className="whitespace-pre-wrap text-sm leading-relaxed">{message.body}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
