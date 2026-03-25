import { Send, Paperclip, Image as ImageIcon, X, Loader2 } from 'lucide-react';
import { useState, useRef, useEffect } from 'react';
import { Attachment } from '../../types';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'motion/react';

interface ChatComposerProps {
  onSend: (text: string, attachments: Attachment[]) => void;
  isThinking: boolean;
  placeholder?: string;
  isReadOnly?: boolean;
}

export default function ChatComposer({ 
  onSend, 
  isThinking, 
  placeholder = "Ask a question...", 
  isReadOnly = false 
}: ChatComposerProps) {
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    if (!input.trim() && attachments.length === 0) return;
    onSend(input, attachments);
    setInput('');
    setAttachments([]);
  };

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files) return;
    
    // Simulate image attachment
    const newAttachments: Attachment[] = Array.from(files).map(file => ({
      id: Math.random().toString(),
      name: file.name,
      type: 'image',
      url: URL.createObjectURL(file),
      file,
      status: 'success',
      size: (file.size / 1024).toFixed(1) + ' KB'
    }));
    setAttachments(prev => [...prev, ...newAttachments]);
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  return (
    <div className="p-3 pt-0">
      <div className="max-w-xl mx-auto">
        <div className={cn(
          "glass-card rounded-[22px] p-2 transition-colors relative overflow-hidden",
          isThinking && "ring-2 ring-accent/15 border-accent/40",
          isReadOnly && "opacity-50 pointer-events-none grayscale"
        )}>
          {/* Image Previews */}
          <AnimatePresence>
            {attachments.length > 0 && (
              <motion.div 
                initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                animate={{ opacity: 1, height: 'auto', marginBottom: 6 }}
                exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                className="flex flex-wrap gap-2 p-2 bg-background rounded-xl border border-border relative z-10"
              >
                {attachments.map((att) => (
                  <motion.div 
                    layout
                    key={att.id} 
                    className="flex items-center gap-1.5 bg-surface-secondary rounded-md px-2 py-1.5 text-[11px] text-foreground border border-border group/att hover:border-accent/30 transition-colors"
                  >
                    <div className="w-4 h-4 bg-accent/10 rounded flex items-center justify-center">
                      <ImageIcon className="w-2.5 h-2.5 text-accent" />
                    </div>
                    <span className="max-w-[120px] truncate font-medium">{att.name}</span>
                    <button 
                      onClick={() => setAttachments(prev => prev.filter(a => a.id !== att.id))}
                      className="p-0.5 hover:text-red-500 transition-all opacity-0 group-hover/att:opacity-100 bg-red-500/10 rounded ml-0.5"
                    >
                      <X className="w-2 h-2" />
                    </button>
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
          
          <div className="flex items-end gap-2 px-1 relative z-10">
            <div className="flex items-center gap-0.5 mb-0.5">
              <button 
                onClick={() => fileInputRef.current?.click()}
                className="p-2 text-muted hover:text-accent transition-colors rounded-lg hover:bg-background border border-transparent hover:border-border group/btn relative overflow-hidden"
                title="Attach image"
              >
                <ImageIcon className="w-4 h-4 group-hover/btn:scale-110 transition-transform relative z-10" />
              </button>
              <input 
                type="file" 
                accept="image/*" 
                multiple 
                ref={fileInputRef} 
                onChange={handleImageUpload} 
                className="hidden" 
              />
              <button className="p-2 text-muted hover:text-foreground transition-colors rounded-lg hover:bg-background border border-transparent hover:border-border group/btn">
                <Paperclip className="w-4 h-4 group-hover/btn:scale-110 transition-transform" />
              </button>
            </div>
            
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder={isReadOnly ? "Read-only" : placeholder}
              className="flex-1 bg-transparent border-none focus:ring-0 text-[15px] font-medium text-foreground py-2.5 min-h-[40px] max-h-[120px] resize-none custom-scrollbar placeholder:text-muted placeholder:font-normal tracking-tight"
              rows={1}
            />
            
            <div className="flex items-center gap-2 mb-0.5">
              {isThinking ? (
                <div className="p-2 bg-accent/10 text-accent rounded-lg border border-accent/20">
                  <Loader2 className="w-4 h-4 animate-spin" />
                </div>
              ) : (
                <button 
                  onClick={handleSend}
                  disabled={!input.trim() && attachments.length === 0}
                  className="p-2.5 bg-accent text-white rounded-lg hover:bg-accent-hover disabled:opacity-50 disabled:bg-surface-secondary disabled:text-muted transition-colors active:scale-95 border border-accent/70 flex items-center justify-center"
                >
                  <Send className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
