from time import sleep
from machine import Pin, PWM

class _1602LikeLCD:
	width: int
	height: int

	def __init__(
		self,
		d_pins: list[Pin],
		e: Pin,
		rw: Pin,
		rs: Pin,
		bkl: PWM|None=None,
		vo: PWM|None=None,
		brightness: float=0,
		contrast: float=0
	):
		"""
		d_pins: list of pins d7-d0 or d7-d4
		e: LCD e pin
		rw: LCD rw pin
		rs: LCD rs pin
		bkl: LCD backlight pin
		vo: LCD vo (contrast) pin
		brightness: initial brightness
		contrast: initial contrast
		"""
		if len(d_pins) not in (_required_pins := [4, 8]):
			raise ValueError(f'Number of data pins must be one of: {', '.join([str(p) for p in _required_pins])}.')
		self.dl = len(d_pins)
		self.d = d_pins
		self.e = e
		self.rs = rs
		self.rw = rw
		self.bkl = bkl
		self.vo = vo

		[p.init(p.OUT) for p in self.d]
		self.e.init(e.OUT)
		self.rw.init(rw.OUT)
		self.rs.init(rs.OUT)

		if self.bkl is not None:
			self.bkl.freq(1024)
			self.bkl.duty_u16(0)
		if self.vo is not None:
			self.vo.freq(1024)
			self.vo.duty_u16(0)

		self.set_brightness(brightness)
		self.set_contrast(contrast)

		self._disp_vis = False
		self._cur_vis = False
		self._blinking = False

		self.reset()

	def _upd_display(self):
		"""Update display attributes"""
		self.send_command([0,0,0,0,1,int(self._disp_vis),int(self._cur_vis),int(self._blinking)])

	def _zero(self):
		"""Set all data and control pins low"""
		[p.off() for p in self.d+[self.e,self.rs,self.rw]]

	def _set_cgram_addr(self, addr: int):
		"""Set the CGRAM address"""
		self.send_command([int(b) for b in f'01{bin(addr)[2:]:0>6}'])

	def _set_ddram_addr(self, addr: int):
		"""Set the DDRAM address"""
		if addr > 40:
			addr += 24
		self.send_command([int(b) for b in f'1{bin(addr)[2:]:0>7}'])

	def _get_ddram_addr(self) -> int:
		"""Return the DDRAM address"""
		self.rs.off()
		addr = int(''.join([str(b) for b in self.read_byte()]), 2)
		if addr >= 64: addr -= 24
		return addr

	def _set_d(self, data: list[int]):
		"""Set the data pins"""
		for i, d in enumerate(data):
			self.d[i].value(d)

	def _send_data(self, data: list[int]):
		"""Pulse the e pin of the LCD with the provided data on the d pins"""
		self.rw.off()
		if self.dl == 4:
			self._set_d(data[:4])
			self.e.on()
			self.e.off()
			self._set_d(data[4:])
			self.e.on()
			self.e.off()
		if self.dl == 8:
			self._set_d(data)
			self.e.on()
			self.e.off()

	def set_visibility(self, value: bool):
		"""Set the LCD visibility bit"""
		self._disp_vis = value
		self._upd_display()

	def set_cur_visibility(self, value: bool):
		"""Set the cursor visibility bit"""
		self._cur_vis = value
		self._upd_display()

	def set_cur_blink(self, value: bool):
		"""Set the cursor blink bit"""
		self._blinking = value
		self._upd_display()

	def set_brightness(self, value: float):
		"""Set the LCD brightness"""
		if self.bkl is None:return
		self.bkl.duty_u16(int(65535 * value))

	def set_contrast(self, value: float):
		"""Set the LCD contrast"""
		if self.vo is None:return
		self.vo.duty_u16(int(65535 * (1-value)))

	def read_byte(self):
		"""Read a byte from the LCD"""
		self.rw.on()
		[p.init(p.IN) for p in self.d]

		data = []

		self.e.on()
		data = [d.value() for d in self.d]
		self.e.off()
		if self.dl == 4:
			self.e.on()
			data += [d.value() for d in self.d]
			self.e.off()

		[p.init(p.OUT) for p in self.d]
		return data

	def wait_ready(self):
		"""Wait until the LCD wait bit is low"""
		self.rs.off()

		while True:
			if self.read_byte()[0] == 0:
				break

	def reset(self):
		"""Attempt to "reset" the LCD to a usable state"""
		# Force 8-bit mode
		self._zero()
		self._set_d([0,0,1,1])
		self.e.on()
		self.e.off()
		sleep(.1)
		self.e.on()
		self.e.off()
		sleep(.1)
		self.e.on()
		self.e.off()
		# Enter 4-bit mode if need be
		if self.dl == 4:
			sleep(.01)
			self._set_d([0,0,1,0])
			self.e.on()
			self.e.off()
		self.send_command([0,0,1,(1 if self.dl == 8 else 0),1,0,0,0])
		self.wait_ready()
		self._upd_display()

	def send_command(self, command: list[int]):
		"""Send data to the LCD command register"""
		self.rs.off()
		self._send_data(command)
		self.wait_ready()

	def putch(self, char: int|str):
		"""Write to DDRAM"""
		if type(char) is str:
			char = ord(char)
		assert type(char) is int
		data = [int(b) for b in f'{bin(char)[2:]:0>8}']
		self.rs.on()
		self._send_data(data)
		self.wait_ready()

	def print(self, *objs, sep=' ', end=''):
		"""Print string(s) to DDRAM"""
		for char in sep.join([str(o) for o in objs])+end:
			self.putch(char)

	def set_cur_pos(self, line: int, column: int):
		"""Set the cursor position (1-based)"""
		# weird
		if line == 1:pass
		elif line == 2:line = 3
		elif line == 3:line = 2
		elif line == 4:pass

		self._set_ddram_addr(((line-1)*20)+column-1)

	def get_cur_pos(self) -> tuple[int, int]:
		"""Get the cursor position (1-based)"""

		addr = self._get_ddram_addr()

		column = addr % 20 + 1
		line = addr // 20 + 1

		if line == 1:pass
		elif line == 2:line = 3
		elif line == 3:line = 2
		elif line == 4:pass

		return line, column

	def clear(self):
		"""Clear the display and set the cursor position to (1,1)"""
		self.send_command([0,0,0,0,0,0,0,1])

	def cur_home(self):
		"""Set the cursor position to (1,1)"""
		self.send_command([0,0,0,0,0,0,1,0])

	def write_cgram(self, char: int, data: list[list[int]]):
		"""Write some bytes to CGRAM"""
		ret = self._get_ddram_addr()

		self._set_cgram_addr(char*8)
		for line in data:
			self.putch(int(''.join([str(b) for b in line]),2))

		self._set_ddram_addr(ret)

class LCD1602(_1602LikeLCD):
	"""LCD of width 16, height 2"""
	width=16
	height=2
class LCD2004(_1602LikeLCD):
	"""LCD of width 20, height 4"""
	width=20
	height=4

class Slide:
	...

class TickingGroup:
	...

class StaticProgressBar:
	...
