; ptplay - minimal Shell MOD player built on Frank Wille's ptplayer (OSCOMPAT=1)
; Usage: ptplay FILE/A,LOOP/S   (stops at song end unless LOOP; Ctrl-C stops)
; Plays through the same replayer Word Salad uses, for checking xrns2xmod output.

	xref	_mt_install
	xref	_mt_remove
	xref	_mt_init
	xref	_mt_end
	xref	_mt_Enable
	xref	_mt_SongEnd

CUSTOM		equ	$dff000
MEMF_CHIP	equ	2
SIGBREAKF_CTRL_C equ	1<<12

; exec.library
_LVOOpenLibrary	equ	-552
_LVOCloseLibrary equ	-414
_LVOAllocMem	equ	-198
_LVOFreeMem	equ	-210
_LVOSetSignal	equ	-306
; dos.library
_LVOOpen	equ	-30
_LVOClose	equ	-36
_LVORead	equ	-42
_LVOSeek	equ	-66
_LVODelay	equ	-198
_LVOIoErr	equ	-132
_LVOPrintFault	equ	-474
_LVOReadArgs	equ	-798
_LVOFreeArgs	equ	-858
_LVOPutStr	equ	-948

MODE_OLDFILE	equ	1005
OFFSET_BEGINNING equ	-1
OFFSET_END	equ	1

	section	code,code

start:
	movem.l	d2-d7/a2-a6,-(sp)
	moveq	#20,d7			; return code: FAIL until proven otherwise
	moveq	#0,d6			; module size
	moveq	#0,d4			; file handle
	sub.l	a5,a5			; module memory
	sub.l	a3,a3			; RDArgs
	move.l	4.w,a6
	lea	dosname(pc),a1
	moveq	#37,d0
	jsr	_LVOOpenLibrary(a6)
	move.l	d0,dosbase
	beq	.exit
	move.l	d0,a6

	; parse FILE/A,LOOP/S
	lea	template(pc),a0
	move.l	a0,d1
	move.l	#argarray,d2
	moveq	#0,d3
	jsr	_LVOReadArgs(a6)
	move.l	d0,a3
	tst.l	d0
	beq	.doserr

	; open the file and find its size
	move.l	argarray,d1
	move.l	#MODE_OLDFILE,d2
	jsr	_LVOOpen(a6)
	move.l	d0,d4
	beq	.doserr
	move.l	d4,d1
	moveq	#0,d2
	moveq	#OFFSET_END,d3
	jsr	_LVOSeek(a6)
	move.l	d4,d1
	moveq	#0,d2
	moveq	#OFFSET_BEGINNING,d3
	jsr	_LVOSeek(a6)
	move.l	d0,d6			; size = position of end
	cmp.l	#1084,d6
	blt	.toosmall

	; load it into Chip RAM, where Paula can reach the samples
	move.l	4.w,a6
	move.l	d6,d0
	moveq	#MEMF_CHIP,d1
	jsr	_LVOAllocMem(a6)
	move.l	d0,a5
	move.l	dosbase,a6
	tst.l	d0
	beq	.nomem
	move.l	d4,d1
	move.l	a5,d2
	move.l	d6,d3
	jsr	_LVORead(a6)
	cmp.l	d6,d0
	bne	.readerr
	move.l	d4,d1
	jsr	_LVOClose(a6)
	moveq	#0,d4

	lea	msgplay(pc),a0
	bsr	puts
	move.l	argarray,a0
	bsr	puts
	lea	msgnl(pc),a0
	bsr	puts

	; play
	jsr	_mt_install
	tst.l	d0
	beq	.noaudio
	lea	CUSTOM,a6
	move.l	a5,a0
	sub.l	a1,a1
	moveq	#0,d0
	jsr	_mt_init
	tst.l	argarray+4		; LOOP?
	bne	.loop
	st	_mt_SongEnd		; -1: stop when the song ends
.loop:
	st	_mt_Enable

.wait:	move.l	dosbase,a6
	moveq	#5,d1
	jsr	_LVODelay(a6)
	move.l	4.w,a6
	moveq	#0,d0
	moveq	#0,d1
	jsr	_LVOSetSignal(a6)
	and.l	#SIGBREAKF_CTRL_C,d0
	bne	.stop
	tst.b	_mt_Enable
	bne	.wait

.stop:	lea	CUSTOM,a6
	jsr	_mt_end
	jsr	_mt_remove
	lea	msgdone(pc),a0
	bsr	puts
	moveq	#0,d7
	bra	.cleanup

.noaudio:
	lea	msgaudio(pc),a0
	bsr	puts
	bra	.cleanup
.toosmall:
	lea	msgsmall(pc),a0
	bsr	puts
	bra	.cleanup
.nomem:
	lea	msgnomem(pc),a0
	bsr	puts
	bra	.cleanup
.readerr:
.doserr:
	move.l	dosbase,a6
	jsr	_LVOIoErr(a6)
	move.l	d0,d1
	lea	progname(pc),a0
	move.l	a0,d2
	jsr	_LVOPrintFault(a6)

.cleanup:
	move.l	dosbase,a6
	tst.l	d4
	beq	.1
	move.l	d4,d1
	jsr	_LVOClose(a6)
.1:	move.l	a3,d1
	beq	.2
	jsr	_LVOFreeArgs(a6)
.2:	move.l	4.w,a6
	move.l	a5,d0
	beq	.3
	move.l	a5,a1
	move.l	d6,d0
	jsr	_LVOFreeMem(a6)
.3:	move.l	dosbase,a1
	jsr	_LVOCloseLibrary(a6)
.exit:	move.l	d7,d0
	movem.l	(sp)+,d2-d7/a2-a6
	rts

; puts(a0=string) via dos PutStr
puts:	move.l	a6,-(sp)
	move.l	dosbase,a6
	move.l	a0,d1
	jsr	_LVOPutStr(a6)
	move.l	(sp)+,a6
	rts

dosname:	dc.b	"dos.library",0
template:	dc.b	"FILE/A,LOOP/S",0
progname:	dc.b	"ptplay",0
msgplay:	dc.b	"Playing ",0
msgnl:		dc.b	" (Ctrl-C stops)",10,0
msgdone:	dc.b	"Stopped.",10,0
msgaudio:	dc.b	"ptplay: audio channels or CIA timer are busy",10,0
msgsmall:	dc.b	"ptplay: file is too small to be a MOD",10,0
msgnomem:	dc.b	"ptplay: not enough Chip RAM",10,0
version:	dc.b	"$VER: ptplay 1.0 (19.10.2026) ptplayer 6.4",0
	even

	section	bss,bss
dosbase:	ds.l	1
argarray:	ds.l	2
