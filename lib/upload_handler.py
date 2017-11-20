# -*- coding: utf-8 -*-
#********************************************************************
# ZYNTHIAN PROJECT: Zynthian Web Configurator
#
# SoundFont Manager Handler
#
# Copyright (C) 2017 Markus Heidt <markus@heidt-tech.com>
#
#********************************************************************
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of
# the License, or any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the LICENSE.txt file.
#
#********************************************************************

import os
import sys
import logging
import tornado.web
import tornado.websocket
import shutil
import datetime

#from lib.post_streamer import PostDataStreamer
from tornadostreamform.multipart_streamer import MultiPartStreamer, StreamedPart, TemporaryFileStreamedPart

#------------------------------------------------------------------------------
# Uoload Handling
#------------------------------------------------------------------------------
MB = 1024 * 1024
GB = 1024 * MB
TB = 1024 * GB
MAX_STREAMED_SIZE = 1*TB

class UploadPostDataStreamer(MultiPartStreamer):
	percent = 0

	def __init__(self, webSocketHandler, destinationPath, total):
		self.webSocketHandler = webSocketHandler
		self.destinationPath = destinationPath
		super(UploadPostDataStreamer, self).__init__(total)


	def on_progress(self, received, total):
		"""Override this function to handle progress of receiving data."""
		if total:
			new_percent = received*100//total
			if new_percent != self.percent:
				self.percent = new_percent
				logging.info("upload progress: " + str(datetime.datetime.now()) + " " + str(new_percent))
				if self.webSocketHandler:
					self.webSocketHandler.write_message(str(new_percent))

	def examine(self):
		print("============= structure =============")
		for idx,part in enumerate(self.parts):
			print("PART #",idx)
			print("    HEADERS")
			for header in part.headers:
				print("        ",repr(header.get("name","")),"=",repr(header.get("value","")))
				params = header.get("params",None)
				if params:
					for pname in params:
						print("            ",repr(pname),"=",repr(params[pname]))
			print("    DATA")
			print("        SIZE: ", part.get_size())
			print("        filename: ",part.get_filename())
			if part.get_size()<80:
				print("        PAYLOAD:",repr(part.get_payload()))
			else:
				print("        PAYLOAD:","<too long...>")



	def data_complete(self):
		super(UploadPostDataStreamer, self).data_complete()
		self.examine()
		for part in self.parts:
			if part.get_size()>0:
				destinationFilename = part.get_filename()
				logging.info("destinationFilename: " + destinationFilename)
				part.move(self.destinationPath + "/" + destinationFilename)

class UploadPollingHandler(tornado.websocket.WebSocketHandler):
	clientId = '1'

	 # the client connected
	def open(self):
		logging.info("New client connected")


	# the client sent the message
	def on_message(self, message):
		logging.info(message)
		self.clientId = message
		self.application.settings['upload_progress_handler'][self.clientId] = self
		logging.info("progress handler set")
		#self.write_message(message)

	# client disconnected
	def on_close(self):
		logging.info("Client disconnected")
		if self.clientId in self.application.settings['upload_progress_handler']:
			del self.application.settings['upload_progress_handler'][self.clientId]



@tornado.web.stream_request_body
class UploadHandler(tornado.web.RequestHandler):

	def get_current_user(self):
		return self.get_secure_cookie("user")

	@tornado.web.authenticated
	def get(self, errors=None):
		# is not really used
		if self.ps and self.ps.percent:
			logging.info("reporting percent: " + self.ps.percent)
			self.write(self.ps.percent)

	def post(self):
		redirectUrl = "#"
		try:
			#self.fout.close()
			self.ps.data_complete()
			# Use parts here!

			try:
				destinationPath = self.get_argument("destinationPath")
				redirectUrl = self.get_argument("redirectUrl")
				last_part = None
				part_count = 0
				for part in  self.ps.parts:
					if part.get_size()>0:
						last_part = part
						part_count += 1

				if last_part:
					redirectUrl += "?ZYNTHIAN_UPLOAD_NEW_FILE="
					if part_count>1:
						redirectUrl += destinationPath
					else:
						redirectUrl += destinationPath + "/" + last_part.get_filename()
			except Exception as e:
				logging.error("copying failed: %s" % e)
				pass


		finally:
			# Don't forget to release temporary files.
			self.ps.release_parts()
            #self.finish()
			self.redirect(redirectUrl)

	def prepare(self):
		try:
			global MAX_STREAMED_SIZE
			if self.request.method.lower() == "post":
				self.request.connection.set_max_body_size(MAX_STREAMED_SIZE)

			total = int(self.request.headers.get("Content-Length","0"))
			client_id = self.get_argument("clientId")
			destinationPath = self.get_argument("destinationPath")
		except:
			total = 0
			client_id = '1'

		upload_progress_handler = None
		if client_id in self.application.settings['upload_progress_handler']:
			upload_progress_handler = self.application.settings['upload_progress_handler'][client_id]
		self.ps = UploadPostDataStreamer(upload_progress_handler,  destinationPath, total ) #,tmpdir="/tmp"
		#self.fout = open("raw_received.dat","wb+")

	def data_received(self, chunk):
		#self.fout.write(chunk)
		self.ps.data_received(chunk)